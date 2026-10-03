from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import usuario_actual
from ..database import get_db
from ..servicios import redondear_pesos

router = APIRouter(prefix="/reportes", tags=["reportes"])


def _limites(dia: date) -> tuple[datetime, datetime]:
    return datetime.combine(dia, datetime.min.time()), datetime.combine(
        dia, datetime.max.time()
    )


def _ventas_validas_del_dia(dia: date):
    desde, hasta = _limites(dia)
    return (
        models.Venta.fecha_hora >= desde,
        models.Venta.fecha_hora <= hasta,
        models.Venta.anulada.is_(False),
    )


@router.get("/dia", response_model=schemas.ResumenDia)
def resumen_del_dia(
    fecha: date | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    dia = fecha or date.today()
    filtros = _ventas_validas_del_dia(dia)

    total, cantidad, mesas = db.execute(
        select(
            func.coalesce(func.sum(models.Venta.total), 0.0),
            func.count(models.Venta.id),
            func.count(func.distinct(models.Venta.mesa)),
        ).where(*filtros)
    ).one()

    por_metodo = [
        schemas.VentasPorMetodo(metodo_pago=metodo, total=float(suma), cantidad=conteo)
        for metodo, suma, conteo in db.execute(
            select(
                models.Venta.metodo_pago,
                func.coalesce(func.sum(models.Venta.total), 0.0),
                func.count(models.Venta.id),
            )
            .where(*filtros)
            .group_by(models.Venta.metodo_pago)
        ).all()
    ]

    nombre = case(
        (models.DetalleVenta.producto_id.is_not(None), models.Producto.nombre),
        else_=models.Plato.nombre,
    )
    mas_vendidos = [
        schemas.ProductoVendido(nombre=n, cantidad=float(c), total=float(t))
        for n, c, t in db.execute(
            select(
                nombre.label("nombre"),
                func.sum(models.DetalleVenta.cantidad),
                func.sum(models.DetalleVenta.subtotal),
            )
            .join(models.Venta, models.DetalleVenta.venta_id == models.Venta.id)
            .outerjoin(models.Producto, models.DetalleVenta.producto_id == models.Producto.id)
            .outerjoin(models.Plato, models.DetalleVenta.plato_id == models.Plato.id)
            .where(*filtros)
            .group_by(nombre)
            .order_by(func.sum(models.DetalleVenta.cantidad).desc())
            .limit(5)
        ).all()
    ]

    # Costo de lo vendido: solo suma las líneas que tienen costo conocido.
    # Las que no, se cuentan aparte para no inflar la utilidad en silencio.
    costo, sin_costo = db.execute(
        select(
            func.coalesce(
                func.sum(models.DetalleVenta.cantidad * models.DetalleVenta.costo_unitario),
                0.0,
            ),
            func.count(models.DetalleVenta.id).filter(
                models.DetalleVenta.costo_unitario.is_(None)
            ),
        )
        .join(models.Venta, models.DetalleVenta.venta_id == models.Venta.id)
        .where(*filtros)
    ).one()

    total = float(total or 0.0)
    costo = redondear_pesos(costo or 0.0)
    utilidad = redondear_pesos(total - costo)

    return schemas.ResumenDia(
        fecha=dia,
        total=total,
        cantidad_ventas=cantidad,
        ticket_promedio=redondear_pesos(total / cantidad) if cantidad else 0.0,
        mesas_atendidas=mesas,
        costo=costo,
        utilidad=utilidad,
        margen_porcentaje=round(utilidad / total * 100, 1) if total else None,
        lineas_sin_costo=sin_costo,
        por_metodo=por_metodo,
        mas_vendidos=mas_vendidos,
    )


@router.get("/comparar")
def comparar_con_semana_pasada(
    fecha: date | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    """Un número solo no dice nada: se compara contra el mismo día de la
    semana pasada, porque un sábado no se parece a un martes."""
    dia = fecha or date.today()
    anterior = dia - timedelta(days=7)

    def total_de(d: date) -> float:
        valor = db.scalar(
            select(func.coalesce(func.sum(models.Venta.total), 0.0)).where(
                *_ventas_validas_del_dia(d)
            )
        )
        return float(valor or 0.0)

    hoy, pasado = total_de(dia), total_de(anterior)
    variacion = ((hoy - pasado) / pasado * 100) if pasado else None

    return {
        "fecha": dia,
        "total": hoy,
        "fecha_comparada": anterior,
        "total_comparado": pasado,
        "variacion_porcentaje": round(variacion, 1) if variacion is not None else None,
    }


@router.get("/rango")
def totales_por_dia(
    desde: date,
    hasta: date,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    inicio, _fin = _limites(desde)
    _ini, fin = _limites(hasta)

    filas = db.execute(
        select(
            func.date(models.Venta.fecha_hora).label("dia"),
            func.coalesce(func.sum(models.Venta.total), 0.0),
            func.count(models.Venta.id),
        )
        .where(
            models.Venta.fecha_hora >= inicio,
            models.Venta.fecha_hora <= fin,
            models.Venta.anulada.is_(False),
        )
        .group_by("dia")
        .order_by("dia")
    ).all()

    return [
        {"fecha": dia, "total": float(total), "cantidad_ventas": cantidad}
        for dia, total, cantidad in filas
    ]
