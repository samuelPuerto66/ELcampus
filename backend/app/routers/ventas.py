from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, servicios
from ..auth import caja, usuario_actual
from ..config import MINUTOS_PARA_ANULAR
from ..database import get_db

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _puede_anular(venta: models.Venta, usuario: models.Usuario, db: Session) -> None:
    """Un vendedor solo deshace su propio error reciente.

    Cobrar en efectivo y anular la venta un rato después es la forma más
    vieja de sacar plata de una caja sin que se note: el inventario vuelve
    a su sitio y el total del día baja como si la venta nunca hubiera
    existido. Por eso anular cualquier otra cosa es del administrador.
    """
    if usuario.rol is models.RolUsuario.administrador:
        return

    if venta.vendedor_id != usuario.id:
        raise HTTPException(
            status_code=403,
            detail="Esa venta la cobró otra persona. Solo un administrador puede anularla.",
        )

    minutos = (datetime.now() - venta.fecha_hora).total_seconds() / 60
    if minutos > MINUTOS_PARA_ANULAR:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Ya pasaron más de {MINUTOS_PARA_ANULAR} minutos desde esa venta. "
                "Pídele a un administrador que la anule."
            ),
        )

    ultima = db.scalar(select(models.Venta).order_by(models.Venta.id.desc()))
    if ultima is not None and ultima.id != venta.id:
        raise HTTPException(
            status_code=403,
            detail="Solo puedes anular la última venta. Para una anterior, llama al administrador.",
        )


@router.post("", response_model=schemas.VentaLeer, status_code=201)
def cobrar(
    datos: schemas.VentaCrear,
    db: Session = Depends(get_db),
    vendedor: models.Usuario = Depends(caja),
):
    servicios.exigir_caja_abierta(db)

    venta = servicios.registrar_venta(
        db,
        vendedor=vendedor,
        tipo=datos.tipo,
        metodo_pago=datos.metodo_pago,
        mesa=datos.mesa,
        items=datos.items,
    )
    db.commit()
    db.refresh(venta)
    return venta


@router.get("", response_model=list[schemas.VentaLeer])
def listar_ventas(
    limite: int = 50,
    dia: date | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    consulta = select(models.Venta).order_by(models.Venta.id.desc())
    if dia is not None:
        consulta = consulta.where(
            models.Venta.fecha_hora >= datetime.combine(dia, datetime.min.time()),
            models.Venta.fecha_hora <= datetime.combine(dia, datetime.max.time()),
        )
    return db.scalars(consulta.limit(limite)).all()


@router.get("/{venta_id}", response_model=schemas.VentaLeer)
def obtener_venta(
    venta_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    venta = db.get(models.Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return venta


@router.post("/{venta_id}/anular", response_model=schemas.VentaLeer)
def anular_venta(
    venta_id: int,
    datos: schemas.VentaAnular,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(caja),
):
    venta = db.get(models.Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    if venta.anulada:
        raise HTTPException(status_code=409, detail="Esa venta ya está anulada")

    _puede_anular(venta, usuario, db)
    servicios.devolver_al_inventario(db, venta, usuario)

    venta.anulada = True
    venta.motivo_anulacion = datos.motivo
    venta.anulada_por_id = usuario.id
    # La hora de la anulación es la que importa para el cuadre: la plata
    # sale del cajón ahora, no el día en que se hizo la venta.
    venta.anulada_en = datetime.now()

    db.commit()
    db.refresh(venta)
    return venta
