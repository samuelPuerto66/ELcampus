"""Reglas del fiado: cuánto debe cada cliente y hasta dónde se le fía.

Lo que debe un cliente no se guarda en ningún lado: se calcula cada vez
sumando lo que se le fió y restando lo que ha abonado. Así nunca puede
quedar un saldo desactualizado — si se anula una venta fiada, la deuda
baja sola, sin que nadie se acuerde de corregirla.
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .formato import plata


def _fiado_por_cliente():
    """Lo fiado en ventas que siguen vigentes, agrupado por cliente."""
    return (
        select(
            models.Venta.cliente_fiado_id,
            func.coalesce(func.sum(models.PagoVenta.monto), 0.0),
        )
        .join(models.Venta, models.PagoVenta.venta_id == models.Venta.id)
        .where(
            models.PagoVenta.metodo == models.MetodoPago.fiado,
            models.Venta.anulada.is_(False),
            models.Venta.cliente_fiado_id.is_not(None),
        )
        .group_by(models.Venta.cliente_fiado_id)
    )


def _abonado_por_cliente():
    """Lo abonado y no anulado, agrupado por cliente."""
    return (
        select(
            models.AbonoFiado.cliente_id,
            func.coalesce(func.sum(models.AbonoFiado.monto), 0.0),
        )
        .where(models.AbonoFiado.anulado.is_(False))
        .group_by(models.AbonoFiado.cliente_id)
    )


def saldos(db: Session) -> dict[int, float]:
    """Lo que debe cada cliente que debe algo. Los que están al día no
    aparecen."""
    deuda: dict[int, float] = {}
    for cliente_id, fiado in db.execute(_fiado_por_cliente()):
        deuda[cliente_id] = float(fiado)
    for cliente_id, abonado in db.execute(_abonado_por_cliente()):
        deuda[cliente_id] = deuda.get(cliente_id, 0.0) - float(abonado)
    return {cliente_id: saldo for cliente_id, saldo in deuda.items() if saldo > 0}


def saldo_de(db: Session, cliente_id: int) -> float:
    return saldos(db).get(cliente_id, 0.0)


def exigir_cupo(
    db: Session, cliente_id: int | None, monto: float
) -> models.ClienteFiado:
    """Frena una venta fiada que no se debe hacer, y devuelve al cliente.

    A quién se le fía lo decide el dueño al registrarlo y ponerle cupo; la
    caja solo puede fiarle a esa gente, y hasta ese monto.
    """
    if cliente_id is None:
        raise HTTPException(status_code=400, detail="Falta decir a quién se le fía.")

    cliente = db.get(models.ClienteFiado, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente de fiado no existe.")
    if not cliente.activo:
        raise HTTPException(
            status_code=409, detail=f"A {cliente.nombre} ya no se le fía."
        )

    if cliente.cupo is not None:
        debe = saldo_de(db, cliente.id)
        if debe + monto > cliente.cupo:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{cliente.nombre} debe {plata(debe)} y su cupo es "
                    f"{plata(cliente.cupo)}: no se le pueden fiar {plata(monto)} más."
                ),
            )
    return cliente
