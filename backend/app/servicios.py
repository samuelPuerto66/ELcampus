"""Reglas de negocio que usan varios routers.

Vive aparte para que cobrar en el mostrador y cobrar una mesa pasen
exactamente por el mismo camino: mismo cálculo, mismo descuento de stock,
mismo registro de movimientos.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def redondear_pesos(valor: float) -> float:
    # El peso colombiano no maneja centavos en caja.
    return float(round(valor))


def turno_abierto(db: Session) -> models.CierreCaja | None:
    return db.scalar(
        select(models.CierreCaja).where(
            models.CierreCaja.estado == models.EstadoCierreCaja.abierto
        )
    )


def exigir_caja_abierta(db: Session) -> models.CierreCaja:
    """Sin turno abierto no se cobra.

    Si se pudiera cobrar sin abrir la caja, esa plata entraría al cajón sin
    que ningún cierre la cuente, y el cuadre del día dejaría de servir.
    """
    turno = turno_abierto(db)
    if turno is None:
        raise HTTPException(
            status_code=409,
            detail="Abre la caja antes de cobrar: indica con cuánto empiezas el turno.",
        )
    return turno


def consolidar(items) -> dict[tuple[str, int, float | None], float]:
    """Escanear el mismo producto dos veces suma cantidad en una sola línea.

    El precio entra en la clave: un ítem que ya trae precio congelado (viene
    de una mesa) no se mezcla con otro del mismo producto a otro precio.
    """
    consolidados: dict[tuple[str, int, float | None], float] = {}
    for item in items:
        es_producto = item.producto_id is not None
        clave = (
            "producto" if es_producto else "plato",
            item.producto_id if es_producto else item.plato_id,
            getattr(item, "precio_unitario", None),
        )
        consolidados[clave] = consolidados.get(clave, 0.0) + item.cantidad
    return consolidados


def _resolver(db: Session, consolidados) -> list[dict]:
    lineas = []
    for (tipo, id_, precio_congelado), cantidad in consolidados.items():
        if tipo == "producto":
            producto = db.get(models.Producto, id_)
            if producto is None:
                raise HTTPException(status_code=404, detail=f"Producto {id_} no encontrado")
            if producto.es_insumo:
                raise HTTPException(
                    status_code=409,
                    detail=f"{producto.nombre} es un insumo de cocina, no se vende suelto.",
                )
            precio_unitario = precio_congelado or producto.precio_de_venta
            costo_unitario = producto.costo
            plato = None
        else:
            plato = db.get(models.Plato, id_)
            if plato is None:
                raise HTTPException(status_code=404, detail=f"Plato {id_} no encontrado")
            producto = None
            precio_unitario = precio_congelado or plato.precio
            costo_unitario = plato.costo_efectivo

        lineas.append(
            {
                "producto": producto,
                "plato": plato,
                "producto_id": id_ if tipo == "producto" else None,
                "plato_id": id_ if tipo == "plato" else None,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "costo_unitario": costo_unitario,
                "subtotal": redondear_pesos(cantidad * precio_unitario),
            }
        )
    return lineas


def _descontar(
    db: Session,
    *,
    producto: models.Producto,
    cuanto: float,
    usuario_id: int,
    venta_id: int,
) -> None:
    # El stock puede quedar negativo a propósito: la caja nunca se bloquea
    # por un conteo desactualizado. Se cobra y se corrige el inventario
    # después.
    producto.stock_actual -= cuanto
    db.add(
        models.MovimientoInventario(
            producto_id=producto.id,
            tipo=models.TipoMovimientoInventario.salida,
            cantidad=cuanto,
            usuario_id=usuario_id,
            venta_id=venta_id,
        )
    )


def registrar_venta(
    db: Session,
    *,
    vendedor: models.Usuario,
    tipo: models.TipoCobro,
    metodo_pago: models.MetodoPago,
    mesa: int | None,
    items,
) -> models.Venta:
    """Cobra y devuelve la venta.

    Todo el cálculo y la validación ocurren antes de escribir: si algo falla,
    no queda ni media venta guardada. El commit lo hace quien llama, para que
    cobrar una mesa (venta + cerrar el pedido) sea una sola operación.
    """
    if not items:
        raise HTTPException(status_code=400, detail="La venta no puede ir vacía")

    lineas = _resolver(db, consolidar(items))
    total = redondear_pesos(sum(linea["subtotal"] for linea in lineas))

    venta = models.Venta(
        tipo=tipo,
        mesa=mesa,
        total=total,
        metodo_pago=metodo_pago,
        vendedor_id=vendedor.id,
    )
    db.add(venta)
    db.flush()

    for linea in lineas:
        db.add(
            models.DetalleVenta(
                venta_id=venta.id,
                producto_id=linea["producto_id"],
                plato_id=linea["plato_id"],
                cantidad=linea["cantidad"],
                precio_unitario=linea["precio_unitario"],
                costo_unitario=linea["costo_unitario"],
                subtotal=linea["subtotal"],
            )
        )
        if linea["producto"] is not None:
            _descontar(
                db,
                producto=linea["producto"],
                cuanto=linea["cantidad"],
                usuario_id=vendedor.id,
                venta_id=venta.id,
            )
        elif linea["plato"] is not None:
            # Vender una picada saca del inventario la carne y el chorizo
            # que lleva. Un plato sin receta no mueve nada.
            for insumo in linea["plato"].insumos:
                _descontar(
                    db,
                    producto=insumo.producto,
                    cuanto=insumo.cantidad * linea["cantidad"],
                    usuario_id=vendedor.id,
                    venta_id=venta.id,
                )

    return venta


def devolver_al_inventario(
    db: Session, venta: models.Venta, usuario: models.Usuario
) -> None:
    """Deshace exactamente lo que esa venta sacó del inventario.

    Se guía por los movimientos que quedaron registrados, no por el
    producto ni por la receta de hoy: si la receta cambió después, se
    devuelve lo que de verdad salió.
    """
    salidas = db.scalars(
        select(models.MovimientoInventario).where(
            models.MovimientoInventario.venta_id == venta.id,
            models.MovimientoInventario.tipo == models.TipoMovimientoInventario.salida,
        )
    ).all()

    for salida in salidas:
        producto = db.get(models.Producto, salida.producto_id)
        producto.stock_actual += salida.cantidad
        db.add(
            models.MovimientoInventario(
                producto_id=producto.id,
                tipo=models.TipoMovimientoInventario.entrada,
                cantidad=salida.cantidad,
                usuario_id=usuario.id,
                venta_id=venta.id,
            )
        )


def precio_de_venta_de(db: Session, *, producto_id: int | None, plato_id: int | None) -> float:
    """El precio que se le congela a un ítem en el momento en que se pide."""
    if producto_id is not None:
        producto = db.get(models.Producto, producto_id)
        if producto is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return producto.precio_de_venta

    plato = db.get(models.Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    return plato.precio


def productos_en_alerta(db: Session) -> list[models.Producto]:
    return list(
        db.scalars(
            select(models.Producto)
            .where(models.Producto.stock_actual <= models.Producto.alerta_minima)
            .order_by(models.Producto.stock_actual)
        )
    )
