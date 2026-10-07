"""Reglas de negocio que usan varios routers.

Vive aparte para que cobrar en el mostrador y cobrar una mesa pasen
exactamente por el mismo camino: mismo cálculo, mismo descuento de stock,
mismo registro de movimientos.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import fiado, models, schemas
from .config import PORCENTAJE_DESCUENTO_LIBRE, hash_del_codigo_admin
from .formato import plata  # noqa: F401  (los routers la usan como servicios.plata)
from .security import verify_password


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


def exigir_codigo_admin(codigo: str | None, *, que_se_quiere: str) -> None:
    """Frena la operación si no viene el código de administrador correcto.

    Es la autorización en el momento: el administrador escribe su código en
    la pantalla del vendedor o del mesero, sin tener que entrar con su
    cuenta. `que_se_quiere` arma el mensaje: "Un descuento de más del 10%".
    """
    if not codigo:
        raise HTTPException(
            status_code=403,
            detail=f"{que_se_quiere} necesita el código de un administrador.",
        )
    guardado = hash_del_codigo_admin()
    if guardado is None or not verify_password(codigo, guardado):
        raise HTTPException(
            status_code=403, detail="Ese código de administrador no es correcto."
        )


def _autorizar_descuento(
    vendedor: models.Usuario, descuento: float, subtotal: float, codigo: str | None
) -> bool:
    """Decide si el descuento pasa. Devuelve si se usó el código de admin.

    Rebajar un poco ("déjelo en veinte mil") lo puede hacer el vendedor
    solo. Más que eso necesita un administrador: cobrar completo en
    efectivo y registrar un descuento grande es la forma de quedarse con
    la diferencia sin que el cajón descuadre.
    """
    if descuento == 0 or vendedor.rol is models.RolUsuario.administrador:
        return False
    if descuento <= subtotal * PORCENTAJE_DESCUENTO_LIBRE / 100:
        return False

    exigir_codigo_admin(
        codigo, que_se_quiere=f"Un descuento de más del {PORCENTAJE_DESCUENTO_LIBRE}%"
    )
    return True


def _repartir_pagos(
    cobro: schemas.Cobro, a_cobrar: float
) -> list[tuple[models.MetodoPago, float]]:
    """Cuánto entra por cada método. Tiene que sumar exacto lo cobrado.

    Si sobrara o faltara aunque sea un peso, el cuadre de caja quedaría
    mal sin que nadie supiera por qué.
    """
    if not cobro.pagos:
        if a_cobrar == 0:
            # Una cortesía completa: no entra plata por ningún lado.
            return []
        return [(cobro.metodo_pago, a_cobrar)]

    por_metodo: dict[models.MetodoPago, float] = {}
    for pago in cobro.pagos:
        por_metodo[pago.metodo] = por_metodo.get(pago.metodo, 0.0) + redondear_pesos(
            pago.monto
        )

    suma = sum(por_metodo.values())
    if suma != a_cobrar:
        diferencia = a_cobrar - suma
        raise HTTPException(
            status_code=400,
            detail=(
                f"Los pagos suman {plata(suma)} y la cuenta es {plata(a_cobrar)}: "
                + (f"faltan {plata(diferencia)}." if diferencia > 0 else f"sobran {plata(-diferencia)}.")
            ),
        )
    return list(por_metodo.items())


def registrar_venta(
    db: Session,
    *,
    vendedor: models.Usuario,
    tipo: models.TipoCobro,
    mesa: int | None,
    items,
    cobro: schemas.Cobro,
) -> models.Venta:
    """Cobra y devuelve la venta.

    Todo el cálculo y la validación ocurren antes de escribir: si algo falla,
    no queda ni media venta guardada. El commit lo hace quien llama, para que
    cobrar una mesa (venta + cerrar el pedido) sea una sola operación.
    """
    if not items:
        raise HTTPException(status_code=400, detail="La venta no puede ir vacía")

    lineas = _resolver(db, consolidar(items))
    subtotal = redondear_pesos(sum(linea["subtotal"] for linea in lineas))

    descuento = redondear_pesos(cobro.descuento)
    motivo = (cobro.motivo_descuento or "").strip() or None
    if descuento > subtotal:
        raise HTTPException(
            status_code=400,
            detail=f"El descuento ({plata(descuento)}) es mayor que la cuenta ({plata(subtotal)}).",
        )
    if descuento > 0 and motivo is None:
        raise HTTPException(
            status_code=400,
            detail="Escribe por qué se hace el descuento: queda en el historial.",
        )
    con_codigo = _autorizar_descuento(
        vendedor, descuento, subtotal, cobro.codigo_autorizacion
    )
    total = subtotal - descuento

    propina = redondear_pesos(cobro.propina)
    if propina > subtotal:
        raise HTTPException(
            status_code=400,
            detail="La propina es más grande que la cuenta. ¿Se fue un cero de más?",
        )

    pagos = _repartir_pagos(cobro, total + propina)

    # Si parte de la cuenta va fiada, se revisa a quién y si le alcanza el
    # cupo antes de escribir nada.
    monto_fiado = sum(monto for metodo, monto in pagos if metodo is models.MetodoPago.fiado)
    cliente_fiado = (
        fiado.exigir_cupo(db, cobro.cliente_fiado_id, monto_fiado) if monto_fiado else None
    )

    if len(pagos) > 1:
        metodo_pago = models.MetodoPago.mixto
    elif pagos:
        metodo_pago = pagos[0][0]
    else:
        metodo_pago = cobro.metodo_pago or models.MetodoPago.efectivo

    venta = models.Venta(
        tipo=tipo,
        mesa=mesa,
        total=total,
        metodo_pago=metodo_pago,
        vendedor_id=vendedor.id,
        descuento=descuento,
        motivo_descuento=motivo if descuento > 0 else None,
        descuento_con_codigo=con_codigo,
        propina=propina,
        cliente_fiado_id=cliente_fiado.id if cliente_fiado else None,
    )
    db.add(venta)
    db.flush()

    for metodo, monto in pagos:
        db.add(models.PagoVenta(venta_id=venta.id, metodo=metodo, monto=monto))

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


def crear_comanda_para_llevar(
    db: Session, venta: models.Venta, nombre: str | None
) -> models.PedidoMesa | None:
    """Manda a la cocina los platos de una venta de mostrador.

    Sin esto, una picada vendida en la caja se cobraba y nadie la cocinaba:
    la cocina solo mira los pedidos de las mesas. Devuelve None si la venta
    no tenía platos (una cerveza no pasa por la cocina).
    """
    platos = [d for d in venta.detalles if d.plato_id is not None]
    if not platos:
        return None

    comanda = models.PedidoMesa(
        mesa=models.MESA_PARA_LLEVAR,
        para_llevar=True,
        nombre_cliente=(nombre or "").strip() or None,
        estado=models.EstadoPedidoMesa.pagado,
        mesero_id=venta.vendedor_id,
        venta_id=venta.id,
    )
    db.add(comanda)
    db.flush()

    for detalle in platos:
        db.add(
            models.DetallePedidoMesa(
                pedido_id=comanda.id,
                plato_id=detalle.plato_id,
                cantidad=detalle.cantidad,
                precio_unitario=detalle.precio_unitario,
                agregado_por_id=venta.vendedor_id,
            )
        )
    return comanda


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
        if producto.es_insumo:
            # Si entrara a la mesa, la mesa quedaría trabada: la caja no
            # podría cobrarla porque un insumo no se vende.
            raise HTTPException(
                status_code=409,
                detail=f"{producto.nombre} es un insumo de cocina, no se vende suelto.",
            )
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
