"""El cuaderno de fiados.

Quién puede hacer qué:
- Registrar clientes, ponerles cupo o dejar de fiarles: solo el
  administrador. A quién se le fía es una decisión del dueño.
- Ver las cuentas y recibir abonos: la caja, que es donde llega la gente
  a pagar.
- Anular un abono mal registrado: solo el administrador, porque un abono en
  efectivo es plata del cajón.

Las ventas fiadas no pasan por aquí: se cobran en la caja como cualquier
venta, con "fiado" como forma de pago (ver servicios.registrar_venta).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import fiado, models, schemas, servicios
from ..auth import caja, solo_admin
from ..database import get_db
from ..formato import plata

router = APIRouter(prefix="/fiado", tags=["fiado"])


def _buscar_cliente(db: Session, cliente_id: int) -> models.ClienteFiado:
    cliente = db.get(models.ClienteFiado, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Ese cliente de fiado no existe.")
    return cliente


def _leer(cliente: models.ClienteFiado, saldo: float) -> schemas.ClienteFiadoLeer:
    return schemas.ClienteFiadoLeer(
        id=cliente.id,
        nombre=cliente.nombre,
        telefono=cliente.telefono,
        cupo=cliente.cupo,
        activo=cliente.activo,
        saldo=saldo,
    )


def _resumen_de_lo_llevado(venta: models.Venta) -> str:
    """'2 × Cerveza, 1 × Papas': para que el cliente reconozca la compra."""
    return ", ".join(f"{d.cantidad:g} × {d.nombre}" for d in venta.detalles)


# ---------------------------------------------------------------- clientes


@router.get("/clientes", response_model=list[schemas.ClienteFiadoLeer])
def listar_clientes(
    incluir_inactivos: bool = False,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(caja),
):
    """Los que más deben primero: son los que hay que cobrar."""
    consulta = select(models.ClienteFiado)
    if not incluir_inactivos:
        consulta = consulta.where(models.ClienteFiado.activo.is_(True))

    saldos = fiado.saldos(db)
    clientes = [_leer(c, saldos.get(c.id, 0.0)) for c in db.scalars(consulta)]
    return sorted(clientes, key=lambda c: (-c.saldo, c.nombre.lower()))


@router.post("/clientes", response_model=schemas.ClienteFiadoLeer, status_code=201)
def crear_cliente(
    datos: schemas.ClienteFiadoCrear,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    # Dos "Don Pedro" en el cuaderno terminan con la deuda de uno cobrada
    # al otro. Se compara sin mayúsculas para no tener "don pedro" aparte.
    repetido = db.scalar(
        select(models.ClienteFiado).where(
            func.lower(models.ClienteFiado.nombre) == datos.nombre.lower()
        )
    )
    if repetido is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Ya hay un cliente llamado {repetido.nombre}. Agrégale el apellido o un apodo.",
        )

    cliente = models.ClienteFiado(**datos.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return _leer(cliente, 0.0)


@router.patch("/clientes/{cliente_id}", response_model=schemas.ClienteFiadoLeer)
def editar_cliente(
    cliente_id: int,
    datos: schemas.ClienteFiadoEditar,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    cliente = _buscar_cliente(db, cliente_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return _leer(cliente, fiado.saldo_de(db, cliente.id))


@router.get("/clientes/{cliente_id}", response_model=schemas.ClienteFiadoDetalle)
def ver_cuenta(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(caja),
):
    """La cuenta del cliente: todo lo que se llevó fiado y todo lo que abonó,
    lo más reciente primero."""
    cliente = _buscar_cliente(db, cliente_id)

    movimientos: list[schemas.MovimientoFiado] = []

    ventas = db.scalars(
        select(models.Venta).where(models.Venta.cliente_fiado_id == cliente.id)
    )
    for venta in ventas:
        fiado_en_esta = sum(
            p.monto for p in venta.pagos if p.metodo is models.MetodoPago.fiado
        )
        movimientos.append(
            schemas.MovimientoFiado(
                tipo="fiado",
                id=venta.id,
                fecha=venta.fecha_hora,
                monto=fiado_en_esta,
                detalle=_resumen_de_lo_llevado(venta),
                anulado=venta.anulada,
            )
        )

    abonos = db.scalars(
        select(models.AbonoFiado).where(models.AbonoFiado.cliente_id == cliente.id)
    )
    for abono in abonos:
        movimientos.append(
            schemas.MovimientoFiado(
                tipo="abono",
                id=abono.id,
                fecha=abono.fecha,
                monto=abono.monto,
                detalle=f"Abono en {abono.metodo.value} · recibió {abono.usuario.nombre}",
                anulado=abono.anulado,
            )
        )

    movimientos.sort(key=lambda m: m.fecha, reverse=True)
    return schemas.ClienteFiadoDetalle(
        **_leer(cliente, fiado.saldo_de(db, cliente.id)).model_dump(),
        movimientos=movimientos,
    )


# ------------------------------------------------------------------ abonos


@router.post(
    "/clientes/{cliente_id}/abonos", response_model=schemas.AbonoLeer, status_code=201
)
def abonar(
    cliente_id: int,
    datos: schemas.AbonoCrear,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(caja),
):
    """El cliente trae plata para pagar lo que debe.

    Necesita la caja abierta por la misma razón que una venta: si entra
    efectivo sin turno, ningún cierre lo cuenta.
    """
    servicios.exigir_caja_abierta(db)
    cliente = _buscar_cliente(db, cliente_id)

    # Recibir más de lo que debe casi siempre es un cero de más; y si de
    # verdad quiere dejar plata adelantada, eso no es un abono.
    debe = fiado.saldo_de(db, cliente.id)
    monto = servicios.redondear_pesos(datos.monto)
    if monto > debe:
        raise HTTPException(
            status_code=400,
            detail=f"{cliente.nombre} solo debe {plata(debe)}.",
        )

    abono = models.AbonoFiado(
        cliente_id=cliente.id, monto=monto, metodo=datos.metodo, usuario_id=usuario.id
    )
    db.add(abono)
    db.commit()
    db.refresh(abono)
    return abono


@router.post("/abonos/{abono_id}/anular", response_model=schemas.AbonoLeer)
def anular_abono(
    abono_id: int,
    datos: schemas.AbonoAnular,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin),
):
    """Para un abono mal registrado. La deuda vuelve a subir, y si era en
    efectivo, el cierre del turno de hoy espera esa plata de menos."""
    abono = db.get(models.AbonoFiado, abono_id)
    if abono is None:
        raise HTTPException(status_code=404, detail="Ese abono no existe.")
    if abono.anulado:
        raise HTTPException(status_code=409, detail="Ese abono ya está anulado.")
    motivo = datos.motivo.strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Escribe por qué se anula el abono.")

    abono.anulado = True
    abono.anulado_en = datetime.now()
    abono.anulado_por_id = admin.id
    abono.motivo_anulacion = motivo
    db.commit()
    db.refresh(abono)
    return abono
