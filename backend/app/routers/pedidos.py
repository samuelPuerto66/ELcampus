from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, servicios
from ..auth import caja, salon, usuario_actual
from ..config import MINUTOS_PARA_CORREGIR
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
    db: Session,
    pedido: models.PedidoMesa,
    datos: schemas.ItemPedidoCrear,
    quien: models.Usuario,
) -> None:
    """Mete un ítem en el pedido, sin confirmar la transacción.

    Pedir lo mismo otra vez suma cantidad, salvo que lleve una nota: "sin
    cebolla" va siempre en su propia línea, para que la cocina la vea.
    """
    existente = None
    if datos.notas is None:
        for detalle in pedido.detalles:
            mismo = (
                detalle.producto_id == datos.producto_id
                and detalle.plato_id == datos.plato_id
                and detalle.notas is None
                # Si la cocina ya despachó ese plato, lo que se pide ahora
                # es un plato nuevo: sumarlo a la línea vieja lo escondería
                # detrás de un "listo" y nadie lo prepararía.
                and detalle.estado_cocina is models.EstadoCocina.pendiente
            )
            if mismo:
                existente = detalle
                break

    if existente is not None:
        existente.cantidad += datos.cantidad
        existente.agregado_por_id = quien.id
        existente.actualizado_en = datetime.now()
        return

    # El precio queda guardado aquí, con el que el cliente pidió. Si el
    # administrador lo cambia mientras la mesa come, esta cuenta no se
    # mueve.
    precio = servicios.precio_de_venta_de(
        db, producto_id=datos.producto_id, plato_id=datos.plato_id
    )

    db.add(
        models.DetallePedidoMesa(
            pedido_id=pedido.id,
            producto_id=datos.producto_id,
            plato_id=datos.plato_id,
            cantidad=datos.cantidad,
            notas=datos.notas,
            precio_unitario=precio,
            agregado_por_id=quien.id,
            actualizado_en=datetime.now(),
        )
    )


def _autorizar_correccion(
    detalle: models.DetallePedidoMesa, usuario: models.Usuario, codigo: str | None
) -> bool:
    """Decide si alguien puede quitar algo ya enviado. Devuelve si hizo
    falta el código del administrador.

    Corregir un error propio recién cometido no necesita a nadie: el mesero
    puso 3 cervezas y eran 2, y lo nota enseguida. Todo lo demás sí: lo que
    envió otra persona, lo que lleva rato en la cuenta, y un plato que la
    cocina ya preparó (quitarlo es botar comida).
    """
    if usuario.rol is models.RolUsuario.administrador:
        return False

    desde = detalle.actualizado_en or detalle.creado_en
    es_propio = detalle.agregado_por_id == usuario.id
    es_reciente = datetime.now() - desde <= timedelta(minutes=MINUTOS_PARA_CORREGIR)
    ya_cocinado = (
        detalle.plato_id is not None
        and detalle.estado_cocina is models.EstadoCocina.listo
    )
    if es_propio and es_reciente and not ya_cocinado:
        return False

    if ya_cocinado:
        que = "Quitar un plato que la cocina ya preparó"
    elif not es_propio:
        que = "Quitar algo que envió otra persona"
    else:
        que = f"Corregir algo enviado hace más de {MINUTOS_PARA_CORREGIR} minutos"
    servicios.exigir_codigo_admin(codigo, que_se_quiere=que)
    return True

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
    if datos.clave is not None:
        ya_llego = db.get(models.EnvioMesa, datos.clave)
        if ya_llego is not None:
            # Es un reintento de algo que ya entró: se devuelve la mesa como
            # está, sin volver a sumar nada.
            return _buscar(db, ya_llego.pedido_id)

    if not datos.items:
        raise HTTPException(
            status_code=400, detail="El pedido está vacío. Agrega algo antes de subirlo."
        )

    # Todo se revisa antes de crear nada. Si un ítem no existe, la mesa no
    # llega a abrirse: es preferible que el mesero reintente a que quede una
    # mesa ocupada con medio pedido dentro.
    for item in datos.items:
        servicios.precio_de_venta_de(
            db, producto_id=item.producto_id, plato_id=item.plato_id
        )

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
        _sumar_item(db, pedido, item, mesero)

    if datos.clave is not None:
        db.add(models.EnvioMesa(clave=datos.clave, pedido_id=pedido.id))

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
    mesero: models.Usuario = Depends(salon),
):
    pedido = _buscar(db, pedido_id)
    _exigir_abierto(pedido)

    _sumar_item(db, pedido, datos, mesero)

    db.commit()
    db.refresh(pedido)
    await tablero.avisar("mesa_actualizada", _resumen(pedido))
    return pedido


@router.post(
    "/{pedido_id}/items/{detalle_id}/quitar", response_model=schemas.PedidoLeer
)
async def quitar_item(
    pedido_id: int,
    detalle_id: int,
    datos: schemas.QuitarItem,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(salon),
):
    """Quita de la mesa algo que ya se había enviado, y deja el registro.

    Es la única forma de bajar lo que debe una mesa: no hay otra puerta que
    cambie cantidades sin dejar rastro.
    """
    pedido = _buscar(db, pedido_id)
    _exigir_abierto(pedido)

    detalle = db.get(models.DetallePedidoMesa, detalle_id)
    if detalle is None or detalle.pedido_id != pedido.id:
        raise HTTPException(status_code=404, detail="Ese ítem no está en esta mesa")
    if datos.cantidad > detalle.cantidad:
        raise HTTPException(
            status_code=400,
            detail=f"En la mesa solo hay {detalle.cantidad:g} de {detalle.nombre}.",
        )

    con_codigo = _autorizar_correccion(detalle, usuario, datos.codigo_autorizacion)

    db.add(
        models.CorreccionPedido(
            pedido_id=pedido.id,
            nombre=detalle.nombre,
            cantidad=datos.cantidad,
            precio_unitario=detalle.precio_unitario,
            motivo=datos.motivo,
            usuario_id=usuario.id,
            con_codigo=con_codigo,
        )
    )

    detalle.cantidad -= datos.cantidad
    # Comparar con un margen y no con cero exacto: 0,3 kg − 0,1 − 0,2 no
    # siempre da 0 en la aritmética del computador.
    if detalle.cantidad < 1e-9:
        db.delete(detalle)

    db.commit()
    db.refresh(pedido)
    # La caja y la cocina se enteran: la cuenta cambió, y si era un plato,
    # ya no hay que prepararlo.
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

    servicios.exigir_caja_abierta(db)

    # El mesero pudo haber agregado algo entre que el cajero leyó la cuenta
    # y le dio a cobrar. Cobrar igual dejaría al cliente pagando una cifra
    # y al sistema registrando otra: el cierre saldría descuadrado.
    if datos.total_esperado is not None and datos.total_esperado != pedido.total:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La cuenta de la mesa {pedido.mesa} cambió: ahora es "
                f"{servicios.plata(pedido.total)}, no {servicios.plata(datos.total_esperado)}. "
                "Revísala con el cliente antes de cobrar."
            ),
        )

    venta = servicios.registrar_venta(
        db,
        vendedor=vendedor,
        tipo=models.TipoCobro.restaurante,
        mesa=pedido.mesa,
        items=pedido.detalles,
        cobro=datos,
    )

    # Cobrar la mesa y cerrarla es una sola operación: nunca puede quedar
    # una venta registrada con la mesa todavía abierta.
    pedido.estado = models.EstadoPedidoMesa.pagado
    pedido.venta_id = venta.id

    db.commit()
    db.refresh(venta)

    await tablero.avisar("mesa_cobrada", {"pedido_id": pedido_id, "mesa": pedido.mesa})
    return venta
