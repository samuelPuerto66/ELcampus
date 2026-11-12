from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import solo_admin, usuario_actual
from ..database import get_db

router = APIRouter(prefix="/platos", tags=["platos"])


@router.get("", response_model=list[schemas.PlatoLeer])
def listar_platos(
    solo_vigentes: bool = True,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    """Los fijos siempre; los especiales solo dentro de sus fechas.

    Un especial sin fechas está en la carta pero NO en el menú: el
    administrador todavía no lo ha sacado para ningún fin de semana. Y el
    que ya pasó se apaga solo, sin que nadie se acuerde el lunes.

    Con `solo_vigentes=false` sale la carta completa, que es lo que el
    administrador necesita para armar el menú del fin de semana.
    """
    consulta = select(models.Plato)
    if solo_vigentes:
        hoy = date.today()
        consulta = consulta.where(
            or_(
                models.Plato.tipo == models.TipoPlato.fijo,
                and_(
                    models.Plato.activo_desde.is_not(None),
                    models.Plato.activo_desde <= hoy,
                    models.Plato.activo_hasta.is_not(None),
                    models.Plato.activo_hasta >= hoy,
                ),
            )
        )
    return db.scalars(consulta.order_by(models.Plato.tipo, models.Plato.nombre)).all()


@router.post("/menu", response_model=list[schemas.PlatoLeer])
def publicar_menu(
    datos: schemas.MenuDelFinDeSemana,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    """Deja en el menú los platos elegidos y saca los demás.

    Es una sola operación a propósito: el administrador marca lo que va, le
    da publicar, y lo que no marcó deja de salirle al mesero. Así no queda
    colgado el especial de la semana pasada por olvido.

    Los platos fijos ni se tocan: la picada, la pechuga y la mojarra van
    todos los fines de semana.
    """
    if datos.hasta < datos.desde:
        raise HTTPException(
            status_code=422, detail="La fecha de fin no puede ser anterior a la de inicio."
        )

    elegidos = set(datos.platos)
    especiales = db.scalars(
        select(models.Plato).where(models.Plato.tipo == models.TipoPlato.especial)
    ).all()

    desconocidos = elegidos - {p.id for p in especiales}
    if desconocidos:
        raise HTTPException(
            status_code=404,
            detail=f"Estos platos no existen o son fijos: {sorted(desconocidos)}",
        )

    for plato in especiales:
        if plato.id in elegidos:
            plato.activo_desde = datos.desde
            plato.activo_hasta = datos.hasta
        else:
            # Fuera del menú, pero sigue en la carta para la próxima.
            plato.activo_desde = None
            plato.activo_hasta = None

    db.commit()
    return listar_platos(solo_vigentes=True, db=db, _=None)


@router.post("", response_model=schemas.PlatoLeer, status_code=201)
def crear_plato(
    datos: schemas.PlatoCrear,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    plato = models.Plato(**datos.model_dump())
    db.add(plato)
    db.commit()
    db.refresh(plato)
    return plato


@router.patch("/{plato_id}", response_model=schemas.PlatoLeer)
def actualizar_plato(
    plato_id: int,
    datos: schemas.PlatoActualizar,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    plato = db.get(models.Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(plato, campo, valor)
    db.commit()
    db.refresh(plato)
    return plato


def _receta(plato: models.Plato) -> schemas.RecetaLeer:
    costo = plato.costo_efectivo
    return schemas.RecetaLeer(
        plato_id=plato.id,
        nombre=plato.nombre,
        precio=plato.precio,
        insumos=[
            schemas.InsumoLeer(
                producto_id=insumo.producto_id,
                nombre=insumo.producto.nombre,
                cantidad=insumo.cantidad,
                costo_unitario=insumo.producto.costo,
                costo_total=(
                    None
                    if insumo.producto.costo is None
                    else float(round(insumo.cantidad * insumo.producto.costo))
                ),
            )
            for insumo in plato.insumos
        ],
        costo=costo,
        utilidad=None if costo is None else float(round(plato.precio - costo)),
    )


@router.get("/{plato_id}/receta", response_model=schemas.RecetaLeer)
def ver_receta(
    plato_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    plato = db.get(models.Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")
    return _receta(plato)


@router.put("/{plato_id}/receta", response_model=schemas.RecetaLeer)
def guardar_receta(
    plato_id: int,
    insumos: list[schemas.InsumoEscribir],
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    """Reemplaza la receta completa. Mandar una lista vacía la quita.

    Desde que un plato tiene receta, venderlo descuenta sus insumos del
    inventario y su costo deja de ser un estimado.
    """
    plato = db.get(models.Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    vistos = set()
    for insumo in insumos:
        producto = db.get(models.Producto, insumo.producto_id)
        if producto is None:
            raise HTTPException(
                status_code=404, detail=f"Producto {insumo.producto_id} no encontrado"
            )
        if insumo.producto_id in vistos:
            raise HTTPException(
                status_code=400,
                detail=f"{producto.nombre} está dos veces en la receta.",
            )
        vistos.add(insumo.producto_id)

    plato.insumos.clear()
    db.flush()
    for insumo in insumos:
        plato.insumos.append(
            models.InsumoPlato(producto_id=insumo.producto_id, cantidad=insumo.cantidad)
        )

    db.commit()
    db.refresh(plato)
    return _receta(plato)


@router.delete("/{plato_id}", status_code=204)
def borrar_plato(
    plato_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    plato = db.get(models.Plato, plato_id)
    if plato is None:
        raise HTTPException(status_code=404, detail="Plato no encontrado")

    ya_se_vendio = db.scalar(
        select(models.DetalleVenta.id).where(models.DetalleVenta.plato_id == plato_id).limit(1)
    )
    if ya_se_vendio:
        raise HTTPException(
            status_code=409,
            detail="Este plato ya tiene ventas registradas. Cámbiale las fechas en vez de borrarlo.",
        )

    en_una_mesa = db.scalar(
        select(models.DetallePedidoMesa.id)
        .where(models.DetallePedidoMesa.plato_id == plato_id)
        .limit(1)
    )
    if en_una_mesa:
        raise HTTPException(
            status_code=409,
            detail="Hay una mesa que pidió este plato y todavía no ha pagado. Bórralo cuando la cobren.",
        )

    db.delete(plato)
    db.commit()
