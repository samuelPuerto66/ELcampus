from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import fiado, models, schemas
from ..auth import solo_admin
from ..database import get_db
from ..servicios import redondear_pesos

# Cuánto se vende y cuánto se gana es información del dueño: el mesero y
# la cocina no tienen por qué ver la utilidad del negocio.
router = APIRouter(
    prefix="/reportes", tags=["reportes"], dependencies=[Depends(solo_admin)]
)


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
):
    dia = fecha or date.today()
    filtros = _ventas_validas_del_dia(dia)
    es_de_mesa = models.Venta.tipo == models.TipoCobro.restaurante

    total, cantidad, mesas, descuentos, cantidad_descuentos, propinas = db.execute(
        select(
            func.coalesce(func.sum(models.Venta.total), 0.0),
            func.count(models.Venta.id),
            # Cada cuenta de mesa cobrada es un grupo atendido. Contar los
            # números de mesa distintos diría "1" aunque la mesa 2 se haya
            # llenado tres veces en la noche.
            func.count(models.Venta.id).filter(es_de_mesa),
            func.coalesce(func.sum(models.Venta.descuento), 0.0),
            func.count(models.Venta.id).filter(models.Venta.descuento > 0),
            func.coalesce(func.sum(models.Venta.propina), 0.0),
        ).where(*filtros)
    ).one()

    # Por pago y no por venta: una cuenta de mitad efectivo y mitad Nequi
    # aparece en los dos, cada uno con su parte.
    por_metodo = [
        schemas.VentasPorMetodo(metodo_pago=metodo, total=float(suma), cantidad=conteo)
        for metodo, suma, conteo in db.execute(
            select(
                models.PagoVenta.metodo,
                func.coalesce(func.sum(models.PagoVenta.monto), 0.0),
                func.count(models.PagoVenta.id),
            )
            .join(models.Venta, models.PagoVenta.venta_id == models.Venta.id)
            # Lo fiado no es plata que entró: va aparte, en fiado_del_dia.
            .where(*filtros, models.PagoVenta.metodo != models.MetodoPago.fiado)
            .group_by(models.PagoVenta.metodo)
            .order_by(func.sum(models.PagoVenta.monto).desc())
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

    fiado_del_dia = db.scalar(
        select(func.coalesce(func.sum(models.PagoVenta.monto), 0.0))
        .join(models.Venta, models.PagoVenta.venta_id == models.Venta.id)
        .where(*filtros, models.PagoVenta.metodo == models.MetodoPago.fiado)
    )
    desde, hasta = _limites(dia)
    abonos_del_dia = db.scalar(
        select(func.coalesce(func.sum(models.AbonoFiado.monto), 0.0)).where(
            models.AbonoFiado.anulado.is_(False),
            models.AbonoFiado.fecha >= desde,
            models.AbonoFiado.fecha <= hasta,
        )
    )

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
        descuentos=float(descuentos or 0.0),
        cantidad_descuentos=cantidad_descuentos,
        propinas=float(propinas or 0.0),
        fiado_del_dia=float(fiado_del_dia or 0.0),
        abonos_del_dia=float(abonos_del_dia or 0.0),
        te_deben=sum(fiado.saldos(db).values()),
    )


@router.get("/novedades", response_model=schemas.NovedadesDia)
def novedades_del_dia(
    fecha: date | None = None,
    db: Session = Depends(get_db),
):
    """Lo que el dueño tiene que poder revisar: qué se anuló y qué se rebajó.

    Las anulaciones van por el día en que se anularon, que es cuando salió
    la plata del cajón — no por el día de la venta original.
    """
    dia = fecha or date.today()
    desde, hasta = _limites(dia)

    anuladas = db.scalars(
        select(models.Venta)
        .where(
            models.Venta.anulada.is_(True),
            models.Venta.anulada_en >= desde,
            models.Venta.anulada_en <= hasta,
        )
        .order_by(models.Venta.anulada_en.desc())
    ).all()

    con_descuento = db.scalars(
        select(models.Venta)
        .where(*_ventas_validas_del_dia(dia), models.Venta.descuento > 0)
        .order_by(models.Venta.fecha_hora.desc())
    ).all()

    correcciones = db.scalars(
        select(models.CorreccionPedido)
        .where(
            models.CorreccionPedido.hora >= desde,
            models.CorreccionPedido.hora <= hasta,
        )
        .order_by(models.CorreccionPedido.hora.desc())
    ).all()

    return schemas.NovedadesDia(
        fecha=dia,
        anulaciones=[
            schemas.Novedad(
                id=v.id,
                hora=v.anulada_en,
                quien=v.anulada_por.nombre if v.anulada_por else v.vendedor.nombre,
                monto=v.a_cobrar,
                motivo=v.motivo_anulacion,
            )
            for v in anuladas
        ],
        descuentos=[
            schemas.Novedad(
                id=v.id,
                hora=v.fecha_hora,
                quien=v.vendedor.nombre,
                monto=v.descuento,
                motivo=v.motivo_descuento,
                con_codigo=v.descuento_con_codigo,
            )
            for v in con_descuento
        ],
        correcciones=[
            schemas.Novedad(
                id=c.id,
                hora=c.hora,
                quien=c.usuario.nombre,
                monto=c.monto,
                motivo=c.motivo,
                con_codigo=c.con_codigo,
                que=f"Mesa {c.pedido.mesa} · {c.cantidad:g} × {c.nombre}",
            )
            for c in correcciones
        ],
    )


@router.get("/comparar")
def comparar_con_semana_pasada(
    fecha: date | None = None,
    db: Session = Depends(get_db),
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
