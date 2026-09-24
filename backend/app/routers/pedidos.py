from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, servicios
from ..auth import caja, salon, usuario_actual
from ..database import get_db
from ..eventos import tablero

router = APIRouter(prefix="/pedidos", tags=["pedidos de mesa"])


def _buscar(db: Session, pedido_id: int) -> models.PedidoMesa:
    pedido = db.get(models.PedidoMesa, pedido_id)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Ese pedido no existe")
    return pedido


def _exigir_abierto(pedido: models.PedidoMesa) -> None:
    if pedido.estado is models.EstadoPedidoMesa.pagado:
        raise HTTPException(
            status_code=409, detail="Esa mesa ya se cobró. Abre una mesa nueva."
        )


def _resumen(pedido: models.PedidoMesa) -> dict:
    return {
        "pedido_id": pedido.id,
        "mesa": pedido.mesa,
        "estado": pedido.estado.value,
        "total": pedido.total,
        "items": len(pedido.detalles),
    }


@router.get("", response_model=list[schemas.PedidoLeer])
def listar_pedidos(
    incluir_pagados: bool = False,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    consulta = select(models.PedidoMesa).order_by(models.PedidoMesa.mesa)
    if not incluir_pagados:
        consulta = consulta.where(
            models.PedidoMesa.estado != models.EstadoPedidoMesa.pagado
        )
    return db.scalars(consulta).all()


@router.get("/{pedido_id}", response_model=schemas.PedidoLeer)
def obtener_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    return _buscar(db, pedido_id)


@router.post("", response_model=schemas.PedidoLeer, status_code=201)
def abrir_mesa(
    datos: schemas.PedidoCrear,
    db: Session = Depends(get_db),
    mesero: models.Usuario = Depends(salon),
):
    ya_abierta = db.scalar(
        select(models.PedidoMesa).where(
            models.PedidoMesa.mesa == datos.mesa,
            models.PedidoMesa.estado != models.EstadoPedidoMesa.pagado,
        )
    )
    if ya_abierta is not None:
        raise HTTPException(
            status_code=409,
            detail=f"La mesa {datos.mesa} ya está abierta. Ábrela desde la lista de mesas.",
        )

    pedido = models.PedidoMesa(mesa=datos.mesa, mesero_id=mesero.id)
    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return pedido


def _sumar_item(
    db: Session, pedido: models.PedidoMesa, datos: schemas.ItemPedidoCrear
) -> None:
    """Mete un ítem en el pedido, sin confirmar la transacción.

    Pedir lo mismo otra vez suma cantidad, salvo que lleve una nota distinta:
    "sin ensalada" y "con ensalada" son dos líneas distintas.
    """
    existente = None
    if datos.notas is None:
        for detalle in pedido.detalles:
            mismo = (
                detalle.producto_id == datos.producto_id
                and detalle.plato_id == datos.plato_id
                and detalle.notas is None
            )
            if mismo:
                existente = detalle
                break

    if existente is not None:
        existente.cantidad += datos.cantidad
        return

    if datos.producto_id is not None and db.get(models.Producto, datos.producto_id) is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    if datos.plato_id is not None and db.get(models.Plato, datos.plato_id) is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    db.add(
        models.DetallePedidoMesa(
            pedido_id=pedido.id,
            producto_id=datos.producto_id,
            plato_id=datos.plato_id,
            cantidad=datos.cantidad,
            notas=datos.notas,
        )
    )


@router.get("/mesa/{numero}", response_model=schemas.PedidoLeer | None)
def pedido_de_la_mesa(
    numero: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    """El pedido abierto de una mesa, o null si la mesa está libre.

    Devuelve null en vez de 404 porque "libre" es una respuesta normal, no
    un error: el mesero abre la mesa 7 y todavía no ha pedido nada.
    """
    return db.scalar(
        select(models.PedidoMesa).where(
            models.PedidoMesa.mesa == numero,
            models.PedidoMesa.estado != models.EstadoPedidoMesa.pagado,
        )
    )


@router.post("/enviar", response_model=schemas.PedidoLeer, status_code=201)
async def enviar_pedido(
    datos: schemas.PedidoEnviar,
    db: Session = Depends(get_db),
    mesero: models.Usuario = Depends(salon),
):
    """Sube de una vez lo que el mesero anotó en el celular.

    Esta es la operación que ocupa la mesa. Si la mesa estaba libre se abre
    aquí, con sus ítems ya dentro; si ya estaba ocupada, lo nuevo se suma a
    lo que había. En ningún caso queda una mesa ocupada y vacía: o entra
    todo, o no entra nada.
    """
    if not datos.items:
        raise HTTPException(
            status_code=400, detail="El pedido está vacío. Agrega algo antes de subirlo."
        )

    # Todo se revisa antes de crear nada. Si un ítem no existe, la mesa no
    # llega a abrirse: es preferible que el mesero reintente a que quede una
    # mesa ocupada con medio pedido dentro.
    for item in datos.items:
        if item.producto_id is not None and db.get(models.Producto, item.producto_id) is None:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        if item.plato_id is not None and db.get(models.Plato, item.plato_id) is None:
            raise HTTPException(status_code=404, detail="Plato no encontrado")

    pedido = db.scalar(
        select(models.PedidoMesa).where(
            models.PedidoMesa.mesa == datos.mesa,
            models.PedidoMesa.estado != models.EstadoPedidoMesa.pagado,
        )
    )
    es_nueva = pedido is None

    if es_nueva:
        pedido = models.PedidoMesa(mesa=datos.mesa, mesero_id=mesero.id)
        db.add(pedido)
        db.flush()

    for item in datos.items:
        _sumar_item(db, pedido, item)

    db.commit()
    db.refresh(pedido)

    await tablero.avisar(
        "mesa_abierta" if es_nueva else "mesa_actualizada", _resumen(pedido)
    )
    return pedido


@router.post("/{pedido_id}/items", response_model=schemas.PedidoLeer, status_code=201)
async def agregar_item(
    pedido_id: int,
    datos: schemas.ItemPedidoCrear,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(salon),
):
    pedido = _buscar(db, pedido_id)
    _exigir_abierto(pedido)

    _sumar_item(db, pedido, datos)

    db.commit()
    db.refresh(pedido)
    await tablero.avisar("mesa_actualizada", _resumen(pedido))
    return pedido


@router.patch("/{pedido_id}/items/{detalle_id}", response_model=schemas.PedidoLeer)
async def cambiar_cantidad(
    pedido_id: int,
    detalle_id: int,
    datos: schemas.ItemPedidoCantidad,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(salon),
):
    pedido = _buscar(db, pedido_id)
    _exigir_abierto(pedido)

    detalle = db.get(models.DetallePedidoMesa, detalle_id)
    if detalle is None or detalle.pedido_id != pedido.id:
        raise HTTPException(status_code=404, detail="Ese ítem no está en esta mesa")

    if datos.cantidad <= 0:
        db.delete(detalle)
    else:
        detalle.cantidad = datos.cantidad

    db.commit()
    db.refresh(pedido)
    await tablero.avisar("mesa_actualizada", _resumen(pedido))
    return pedido


@router.post("/{pedido_id}/pedir-cuenta", response_model=schemas.PedidoLeer)
async def pedir_cuenta(
    pedido_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(salon),
):
    """El momento en que el pedido salta solo a la pantalla de la caja."""
    pedido = _buscar(db, pedido_id)
    _exigir_abierto(pedido)

    if not pedido.detalles:
        raise HTTPException(
            status_code=400, detail="Esta mesa no tiene nada pedido todavía."
        )

    pedido.estado = models.EstadoPedidoMesa.cuenta_pedida
    pedido.hora_cuenta_pedida = datetime.now()
    db.commit()
    db.refresh(pedido)

    await tablero.avisar("cuenta_pedida", _resumen(pedido))
    return pedido


@router.post("/{pedido_id}/cobrar", response_model=schemas.VentaLeer)
async def cobrar_mesa(
    pedido_id: int,
    datos: schemas.VentaDesdePedido,
    db: Session = Depends(get_db),
    vendedor: models.Usuario = Depends(caja),
):
    pedido = _buscar(db, pedido_id)
    _exigir_abierto(pedido)
    if not pedido.detalles:
        raise HTTPException(status_code=400, detail="Esta mesa no tiene nada pedido.")

    venta = servicios.registrar_venta(
        db,
        vendedor=vendedor,
        tipo=models.TipoCobro.restaurante,
        metodo_pago=datos.metodo_pago,
        mesa=pedido.mesa,
        items=pedido.detalles,
    )

    # Cobrar la mesa y cerrarla es una sola operación: nunca puede quedar
    # una venta registrada con la mesa todavía abierta.
    pedido.estado = models.EstadoPedidoMesa.pagado
    pedido.venta_id = venta.id

    db.commit()
    db.refresh(venta)

    await tablero.avisar("mesa_cobrada", {"pedido_id": pedido_id, "mesa": pedido.mesa})
    return venta
