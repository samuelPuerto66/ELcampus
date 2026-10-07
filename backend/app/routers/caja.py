from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models, schemas, servicios
from ..auth import caja as rol_caja
from ..database import get_db

router = APIRouter(prefix="/caja", tags=["caja"])


def _turno_abierto(db: Session) -> models.CierreCaja | None:
    return servicios.turno_abierto(db)


def _efectivo_del_turno(db: Session, desde: datetime, hasta: datetime) -> float:
    """Lo que debería haber entrado al cajón en efectivo durante el turno.

    Se cuenta por el momento en que la plata se mueve, no por la fecha de la
    venta: lo cobrado entra cuando se cobra, y lo devuelto sale cuando se
    anula. Si se midiera solo por la fecha de la venta, anular hoy algo
    cobrado ayer dejaría el cajón corto y el cierre reportaría un faltante
    que en realidad es una devolución.
    """
    # Solo la parte en efectivo de cada venta: si pagaron mitad por Nequi,
    # esa mitad nunca pasó por el cajón. Las propinas en efectivo sí entran.
    efectivo = (
        select(func.coalesce(func.sum(models.PagoVenta.monto), 0.0))
        .join(models.Venta, models.PagoVenta.venta_id == models.Venta.id)
        .where(models.PagoVenta.metodo == models.MetodoPago.efectivo)
    )

    # Todo lo cobrado en el turno, incluso lo que después se anuló: esa
    # plata sí entró al cajón.
    entradas = db.scalar(
        efectivo.where(
            models.Venta.fecha_hora >= desde,
            models.Venta.fecha_hora <= hasta,
        )
    )

    # Todo lo devuelto durante el turno, sin importar de qué día sea la
    # venta original.
    salidas = db.scalar(
        efectivo.where(
            models.Venta.anulada.is_(True),
            models.Venta.anulada_en >= desde,
            models.Venta.anulada_en <= hasta,
        )
    )

    # Los abonos de fiado en efectivo también entran al cajón, y si un
    # administrador anula uno durante el turno, esa plata se devuelve.
    abonos_en_efectivo = select(
        func.coalesce(func.sum(models.AbonoFiado.monto), 0.0)
    ).where(models.AbonoFiado.metodo == models.MetodoPago.efectivo)
    abonos = db.scalar(
        abonos_en_efectivo.where(
            models.AbonoFiado.fecha >= desde,
            models.AbonoFiado.fecha <= hasta,
        )
    )
    abonos_devueltos = db.scalar(
        abonos_en_efectivo.where(
            models.AbonoFiado.anulado.is_(True),
            models.AbonoFiado.anulado_en >= desde,
            models.AbonoFiado.anulado_en <= hasta,
        )
    )

    return (
        float(entradas or 0.0)
        - float(salidas or 0.0)
        + float(abonos or 0.0)
        - float(abonos_devueltos or 0.0)
    )


@router.get("/actual", response_model=schemas.CierreCajaLeer | None)
def turno_actual(db: Session = Depends(get_db), _: models.Usuario = Depends(rol_caja)):
    return _turno_abierto(db)


@router.post("/abrir", response_model=schemas.CierreCajaLeer, status_code=201)
def abrir_caja(
    datos: schemas.AbrirCaja,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(rol_caja),
):
    if _turno_abierto(db) is not None:
        raise HTTPException(
            status_code=409, detail="Ya hay una caja abierta. Ciérrala antes de abrir otra."
        )

    turno = models.CierreCaja(
        fecha=date.today(),
        base_inicial=datos.base_inicial,
        usuario_id=usuario.id,
    )
    db.add(turno)
    db.commit()
    db.refresh(turno)
    return turno


@router.post("/cerrar", response_model=schemas.CierreCajaLeer)
def cerrar_caja(
    datos: schemas.CerrarCaja,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(rol_caja),
):
    """Cuadre del día: lo que debería haber en el cajón contra lo contado.

    La diferencia se guarda tal cual, sin corregirla: un descuadre que se
    esconde es un descuadre que se repite.
    """
    turno = _turno_abierto(db)
    if turno is None:
        raise HTTPException(status_code=409, detail="No hay ninguna caja abierta.")

    cierre = datetime.now()
    esperado = servicios.redondear_pesos(
        turno.base_inicial + _efectivo_del_turno(db, turno.hora_apertura, cierre)
    )
    turno.efectivo_esperado = esperado
    turno.efectivo_contado = datos.efectivo_contado
    turno.diferencia = servicios.redondear_pesos(datos.efectivo_contado - esperado)
    turno.hora_cierre = cierre
    turno.estado = models.EstadoCierreCaja.cerrado

    db.commit()
    db.refresh(turno)
    return turno


@router.get("", response_model=list[schemas.CierreCajaLeer])
def historial(
    limite: int = 30,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(rol_caja),
):
    return db.scalars(
        select(models.CierreCaja).order_by(models.CierreCaja.id.desc()).limit(limite)
    ).all()
