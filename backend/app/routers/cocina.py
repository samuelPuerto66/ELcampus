from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import cocina as rol_cocina
from ..database import get_db
from ..eventos import tablero

router = APIRouter(prefix="/cocina", tags=["cocina"])


def _comanda(detalle: models.DetallePedidoMesa) -> schemas.ItemComanda:
    return schemas.ItemComanda(
        id=detalle.id,
        pedido_id=detalle.pedido_id,
        mesa=detalle.pedido.mesa,
        nombre=detalle.nombre,
        cantidad=detalle.cantidad,
        notas=detalle.notas,
        estado_cocina=detalle.estado_cocina,
        creado_en=detalle.creado_en,
    )


def _buscar(db: Session, detalle_id: int) -> models.DetallePedidoMesa:
    detalle = db.get(models.DetallePedidoMesa, detalle_id)
    if detalle is None or detalle.plato_id is None:
        raise HTTPException(status_code=404, detail="Ese plato no está en ninguna comanda")
    return detalle


@router.get("/pendientes", response_model=list[schemas.ItemComanda])
def pendientes(
    incluir_listos: bool = False,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(rol_cocina),
):
    """Lo que la cocina tiene que preparar, lo más viejo primero.

    Solo platos: una cerveza no se cocina. Y solo de mesas sin cobrar —
    una mesa ya pagada no tiene nada pendiente en la parrilla.
    """
    consulta = (
        select(models.DetallePedidoMesa)
        .join(models.PedidoMesa)
        .where(
            models.DetallePedidoMesa.plato_id.is_not(None),
            models.PedidoMesa.estado != models.EstadoPedidoMesa.pagado,
        )
        .order_by(models.DetallePedidoMesa.creado_en)
    )
    if not incluir_listos:
        consulta = consulta.where(
            models.DetallePedidoMesa.estado_cocina == models.EstadoCocina.pendiente
        )

    return [_comanda(detalle) for detalle in db.scalars(consulta)]


@router.post("/items/{detalle_id}/listo", response_model=schemas.ItemComanda)
async def marcar_listo(
    detalle_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(rol_cocina),
):
    detalle = _buscar(db, detalle_id)
    detalle.estado_cocina = models.EstadoCocina.listo
    db.commit()
    db.refresh(detalle)

    # El mesero ve en su celular que ya puede recoger el plato.
    await tablero.avisar(
        "plato_listo",
        {"mesa": detalle.pedido.mesa, "nombre": detalle.nombre, "detalle_id": detalle.id},
    )
    return _comanda(detalle)


@router.post("/items/{detalle_id}/deshacer", response_model=schemas.ItemComanda)
async def volver_a_pendiente(
    detalle_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(rol_cocina),
):
    """Por si se marcó listo el plato equivocado."""
    detalle = _buscar(db, detalle_id)
    detalle.estado_cocina = models.EstadoCocina.pendiente
    db.commit()
    db.refresh(detalle)

    await tablero.avisar("cocina_actualizada", {"mesa": detalle.pedido.mesa})
    return _comanda(detalle)
