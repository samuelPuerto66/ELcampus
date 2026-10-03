"""Controles sobre el dinero: quién puede anular, cómo cuadra la caja y
cuándo se congela un precio.

Cada prueba de aquí corresponde a un agujero real que tenía el sistema.
"""

from datetime import datetime, timedelta

import pytest

from app import models


def _cobrar(cliente, producto_id, cantidad=1, metodo="efectivo"):
    return cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": metodo,
            "items": [{"producto_id": producto_id, "cantidad": cantidad}],
        },
    ).json()


def _envejecer(db, venta_id: int, minutos: int) -> None:
    venta = db.get(models.Venta, venta_id)
    venta.fecha_hora = datetime.now() - timedelta(minutes=minutos)
    db.commit()


# --------------------------------------------------- quién puede anular


def test_el_vendedor_deshace_su_propia_ultima_venta(cliente, datos):
    venta = _cobrar(cliente, datos["cerveza"].id, 2)

    respuesta = cliente.post(
        f"/api/ventas/{venta['id']}/anular", json={"motivo": "me equivoqué"}
    )

    assert respuesta.status_code == 200
    assert datos["cerveza"].stock_actual == 100


def test_el_vendedor_no_puede_anular_una_venta_vieja(cliente, db, datos):
    venta = _cobrar(cliente, datos["cerveza"].id, 2)
    _envejecer(db, venta["id"], minutos=30)

    respuesta = cliente.post(
        f"/api/ventas/{venta['id']}/anular", json={"motivo": "ya pasó un rato"}
    )

    assert respuesta.status_code == 403
    assert "administrador" in respuesta.json()["detail"]
    # La plata y el stock se quedan como estaban.
    assert datos["cerveza"].stock_actual == 98


def test_el_vendedor_no_puede_anular_una_venta_que_no_es_la_ultima(cliente, datos):
    primera = _cobrar(cliente, datos["cerveza"].id, 2)
    _cobrar(cliente, datos["cerveza"].id, 1)

    respuesta = cliente.post(
        f"/api/ventas/{primera['id']}/anular", json={"motivo": "esta de atrás"}
    )

    assert respuesta.status_code == 403
    assert "última venta" in respuesta.json()["detail"]


def test_el_vendedor_no_puede_anular_la_venta_de_otra_persona(cliente, como, datos):
    admin = como("admin")
    ajena = _cobrar(admin, datos["cerveza"].id, 2)

    respuesta = cliente.post(
        f"/api/ventas/{ajena['id']}/anular", json={"motivo": "no es mía"}
    )

    assert respuesta.status_code == 403
    assert "otra persona" in respuesta.json()["detail"]


def test_el_administrador_puede_anular_cualquier_venta(cliente, como, db, datos):
    venta = _cobrar(cliente, datos["cerveza"].id, 4)
    _envejecer(db, venta["id"], minutos=300)

    respuesta = como("admin").post(
        f"/api/ventas/{venta['id']}/anular", json={"motivo": "devolución del cliente"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["anulada"] is True
    assert datos["cerveza"].stock_actual == 100


# ------------------------------------------------- el cuadre de la caja


@pytest.mark.sin_caja
def test_anular_una_venta_de_otro_turno_no_inventa_un_faltante(cliente, como, db, datos):
    """El agujero viejo: la plata salía del cajón de hoy y el cierre la
    reportaba como faltante, porque la venta era de ayer."""
    # Turno 1: se cobra en efectivo y se cierra cuadrado.
    cliente.post("/api/caja/abrir", json={"base_inicial": 100000})
    venta = _cobrar(cliente, datos["cerveza"].id, 3)  # 10.500
    primero = cliente.post("/api/caja/cerrar", json={"efectivo_contado": 110500}).json()
    assert primero["diferencia"] == 0

    # Turno 2: se anula la venta de antes, así que salen 10.500 del cajón.
    cliente.post("/api/caja/abrir", json={"base_inicial": 100000})
    _envejecer(db, venta["id"], minutos=600)
    como("admin").post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "devolución"})

    segundo = cliente.post("/api/caja/cerrar", json={"efectivo_contado": 89500}).json()

    assert segundo["efectivo_esperado"] == 89500
    assert segundo["diferencia"] == 0


@pytest.mark.sin_caja
def test_anular_dentro_del_mismo_turno_deja_la_caja_igual(cliente, datos):
    cliente.post("/api/caja/abrir", json={"base_inicial": 50000})
    venta = _cobrar(cliente, datos["cerveza"].id, 2)  # 7.000 entran
    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "se arrepintió"})

    # Entraron 7.000 y volvieron a salir: el cajón quedó como empezó.
    cierre = cliente.post("/api/caja/cerrar", json={"efectivo_contado": 50000}).json()

    assert cierre["efectivo_esperado"] == 50000
    assert cierre["diferencia"] == 0


@pytest.mark.sin_caja
def test_no_se_puede_cobrar_sin_abrir_la_caja(cliente, datos):
    respuesta = cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": datos["cerveza"].id, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409
    assert "Abre la caja" in respuesta.json()["detail"]
    assert datos["cerveza"].stock_actual == 100


@pytest.mark.sin_caja
def test_tampoco_se_puede_cobrar_una_mesa_sin_abrir_la_caja(cliente, como, datos):
    mesero = como("mesero")
    pedido = mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 3, "items": [{"plato_id": datos["picada"].id, "cantidad": 1}]},
    ).json()

    respuesta = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"}
    )

    assert respuesta.status_code == 409


# ------------------------------------------- el precio que vio el cliente


def test_subir_un_precio_no_cambia_lo_que_la_mesa_ya_pidio(cliente, como, datos):
    mesero = como("mesero")
    admin = como("admin")

    pedido = mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 5, "items": [{"plato_id": datos["picada"].id, "cantidad": 1}]},
    ).json()
    assert pedido["total"] == 45000

    admin.patch(f"/api/platos/{datos['picada'].id}", json={"precio": 60000})

    # La mesa sigue debiendo lo que le dijeron.
    de_nuevo = mesero.get(f"/api/pedidos/{pedido['id']}").json()
    assert de_nuevo["total"] == 45000

    # Y se cobra por ese precio, no por el nuevo.
    venta = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"}
    ).json()
    assert venta["total"] == 45000


def test_lo_que_se_pida_despues_del_cambio_sí_va_al_precio_nuevo(cliente, como, datos):
    mesero = como("mesero")
    como("admin").patch(f"/api/platos/{datos['picada'].id}", json={"precio": 50000})

    pedido = mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 6, "items": [{"plato_id": datos["picada"].id, "cantidad": 1}]},
    ).json()

    assert pedido["total"] == 50000


# ------------------------------------------------------------ utilidad


def test_el_reporte_dice_cuanto_se_gano_no_solo_cuanto_se_vendio(cliente, datos):
    # Cerveza: se vende a 3.500 y cuesta 2.300 → deja 1.200 cada una.
    _cobrar(cliente, datos["cerveza"].id, 10)

    resumen = cliente.get("/api/reportes/dia").json()

    assert resumen["total"] == 35000
    assert resumen["costo"] == 23000
    assert resumen["utilidad"] == 12000
    assert resumen["margen_porcentaje"] == 34.3
    assert resumen["lineas_sin_costo"] == 0


def test_la_utilidad_avisa_cuando_falta_saber_un_costo(cliente, datos):
    # La picada no tiene costo cargado: su utilidad aparecería inflada.
    cliente.post(
        "/api/ventas",
        json={
            "tipo": "restaurante",
            "metodo_pago": "efectivo",
            "mesa": 2,
            "items": [
                {"producto_id": datos["cerveza"].id, "cantidad": 2},
                {"plato_id": datos["picada"].id, "cantidad": 1},
            ],
        },
    )

    resumen = cliente.get("/api/reportes/dia").json()

    assert resumen["total"] == 52000
    assert resumen["costo"] == 4600  # solo las dos cervezas
    assert resumen["lineas_sin_costo"] == 1


def test_cambiar_el_costo_no_reescribe_la_utilidad_de_lo_ya_vendido(cliente, como, datos):
    _cobrar(cliente, datos["cerveza"].id, 10)
    antes = cliente.get("/api/reportes/dia").json()["utilidad"]

    como("admin").patch(f"/api/productos/{datos['cerveza'].id}", json={"costo": 3400})

    assert cliente.get("/api/reportes/dia").json()["utilidad"] == antes


# ------------------------------------------------------------ respaldos


def test_la_copia_de_seguridad_queda_abierta_y_completa(tmp_path):
    import sqlite3

    from app.respaldos import copiar

    destino = tmp_path / "copia.db"
    copiar(destino)

    con = sqlite3.connect(destino)
    try:
        tablas = {
            fila[0]
            for fila in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()

    assert {"ventas", "productos", "usuarios"} <= tablas
