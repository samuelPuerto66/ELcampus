"""Pagos divididos, propinas y descuentos.

Las tres tocan el cuadre de caja, así que casi todas las pruebas terminan
mirando lo mismo: que el efectivo que el sistema espera en el cajón sea
exactamente el que de verdad entró.
"""

import pytest

from app import config
from app.security import hash_password

CODIGO = "brasa-2026"


@pytest.fixture
def codigo_puesto(tmp_path, monkeypatch):
    archivo = tmp_path / ".codigo-admin"
    archivo.write_text(hash_password(CODIGO), encoding="utf-8")
    monkeypatch.setattr(config, "ARCHIVO_CODIGO_ADMIN", archivo)


def _vender(cliente, datos, cantidad=2, **cobro):
    """Cervezas a $3.500 en el mostrador, con el cobro que se le pase."""
    cuerpo = {
        "tipo": "mostrador",
        "items": [{"producto_id": datos["cerveza"].id, "cantidad": cantidad}],
        **cobro,
    }
    cuerpo.setdefault("metodo_pago", None if "pagos" in cobro else "efectivo")
    return cliente.post("/api/ventas", json=cuerpo)


def _efectivo_esperado(cliente) -> float:
    """Cierra la caja contando cero y devuelve lo que el sistema esperaba."""
    return cliente.post("/api/caja/cerrar", json={"efectivo_contado": 0}).json()[
        "efectivo_esperado"
    ]


# ----------------------------------------------------------- pagos mixtos


def test_mitad_efectivo_mitad_nequi(cliente, datos):
    r = _vender(
        cliente,
        datos,
        cantidad=4,  # $14.000
        pagos=[{"metodo": "efectivo", "monto": 8000}, {"metodo": "nequi", "monto": 6000}],
    )
    assert r.status_code == 201
    venta = r.json()
    assert venta["total"] == 14000
    assert venta["metodo_pago"] == "mixto"
    assert {p["metodo"]: p["monto"] for p in venta["pagos"]} == {
        "efectivo": 8000,
        "nequi": 6000,
    }


def test_el_cierre_solo_espera_la_parte_en_efectivo(cliente, datos):
    _vender(
        cliente,
        datos,
        cantidad=4,
        pagos=[{"metodo": "efectivo", "monto": 8000}, {"metodo": "nequi", "monto": 6000}],
    )
    # Si contara la venta completa, el cierre diría que faltan $6.000 que
    # en realidad están en Nequi.
    assert _efectivo_esperado(cliente) == 8000


def test_los_pagos_tienen_que_sumar_exacto(cliente, datos):
    r = _vender(
        cliente,
        datos,
        cantidad=4,  # $14.000
        pagos=[{"metodo": "efectivo", "monto": 8000}, {"metodo": "nequi", "monto": 5000}],
    )
    assert r.status_code == 400
    assert "faltan $1.000" in r.json()["detail"]

    r = _vender(
        cliente,
        datos,
        cantidad=4,
        pagos=[{"metodo": "efectivo", "monto": 10000}, {"metodo": "nequi", "monto": 5000}],
    )
    assert r.status_code == 400
    assert "sobran $1.000" in r.json()["detail"]


def test_un_pago_dividido_que_no_cuadra_no_deja_nada_guardado(cliente, datos):
    _vender(
        cliente,
        datos,
        pagos=[{"metodo": "efectivo", "monto": 1}, {"metodo": "nequi", "monto": 1}],
    )
    assert cliente.get("/api/ventas").json() == []
    assert cliente.get(f"/api/productos/{datos['cerveza'].id}").json()["stock_actual"] == 100


def test_anular_un_pago_mixto_solo_saca_del_cajon_lo_que_entro_en_efectivo(
    cliente, datos
):
    venta = _vender(
        cliente,
        datos,
        cantidad=4,
        pagos=[{"metodo": "efectivo", "monto": 8000}, {"metodo": "nequi", "monto": 6000}],
    ).json()
    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "error"})

    assert _efectivo_esperado(cliente) == 0


def test_el_reporte_reparte_el_pago_mixto_entre_sus_metodos(cliente, datos, ver_resumen):
    _vender(
        cliente,
        datos,
        cantidad=4,
        pagos=[{"metodo": "efectivo", "monto": 8000}, {"metodo": "nequi", "monto": 6000}],
    )
    _vender(cliente, datos, cantidad=2, metodo_pago="nequi")  # $7.000

    por_metodo = {m["metodo_pago"]: m["total"] for m in ver_resumen()["por_metodo"]}
    assert por_metodo == {"efectivo": 8000, "nequi": 13000}


def test_no_se_puede_mandar_un_pago_que_diga_mixto(cliente, datos):
    r = _vender(cliente, datos, pagos=[{"metodo": "mixto", "monto": 7000}])
    assert r.status_code == 422


def test_cobrar_una_mesa_con_pago_dividido(cliente, como, datos):
    mesero = como("mesero")
    pedido = mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 3, "items": [{"plato_id": datos["picada"].id, "cantidad": 1}]},
    ).json()

    r = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar",
        json={
            "pagos": [
                {"metodo": "efectivo", "monto": 20000},
                {"metodo": "tarjeta", "monto": 25000},
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["metodo_pago"] == "mixto"
    assert _efectivo_esperado(cliente) == 20000


# ---------------------------------------------------------------- propinas


def test_la_propina_no_cuenta_como_venta_del_negocio(cliente, datos, ver_resumen):
    r = _vender(cliente, datos, propina=700)
    venta = r.json()
    assert venta["total"] == 7000
    assert venta["propina"] == 700
    assert venta["a_cobrar"] == 7700

    resumen = ver_resumen()
    assert resumen["total"] == 7000
    assert resumen["propinas"] == 700
    # La utilidad sale de lo vendido, no de la propina de los empleados.
    assert resumen["utilidad"] == 7000 - 4600


def test_la_propina_en_efectivo_si_esta_en_el_cajon(cliente, datos):
    _vender(cliente, datos, propina=700)
    assert _efectivo_esperado(cliente) == 7700


def test_el_pago_dividido_tiene_que_incluir_la_propina(cliente, datos):
    r = _vender(
        cliente,
        datos,
        propina=700,
        pagos=[{"metodo": "efectivo", "monto": 4000}, {"metodo": "nequi", "monto": 3000}],
    )
    assert r.status_code == 400
    assert "faltan $700" in r.json()["detail"]

    r = _vender(
        cliente,
        datos,
        propina=700,
        pagos=[{"metodo": "efectivo", "monto": 4700}, {"metodo": "nequi", "monto": 3000}],
    )
    assert r.status_code == 201
    assert _efectivo_esperado(cliente) == 4700


def test_una_propina_absurda_se_frena(cliente, datos):
    # El cajero quiso escribir 700 y se le fue un cero... o tres.
    r = _vender(cliente, datos, propina=700000)
    assert r.status_code == 400
    assert "cero de más" in r.json()["detail"]


def test_la_propina_no_puede_ser_negativa(cliente, datos):
    assert _vender(cliente, datos, propina=-100).status_code == 422


# -------------------------------------------------------------- descuentos


def test_un_descuento_chico_lo_da_el_vendedor_solo(cliente, datos, ver_resumen):
    # $7.000 -> "déjelo en $6.500": 7% de descuento.
    r = _vender(cliente, datos, descuento=500, motivo_descuento="cliente frecuente")
    assert r.status_code == 201
    venta = r.json()
    assert venta["subtotal"] == 7000
    assert venta["descuento"] == 500
    assert venta["total"] == 6500

    resumen = ver_resumen()
    assert resumen["total"] == 6500
    assert resumen["descuentos"] == 500
    assert resumen["cantidad_descuentos"] == 1


def test_el_descuento_sale_del_efectivo_esperado(cliente, datos):
    _vender(cliente, datos, descuento=500, motivo_descuento="redondeo")
    assert _efectivo_esperado(cliente) == 6500


def test_todo_descuento_necesita_motivo(cliente, datos):
    r = _vender(cliente, datos, descuento=500)
    assert r.status_code == 400
    assert "por qué" in r.json()["detail"]

    r = _vender(cliente, datos, descuento=500, motivo_descuento="   ")
    assert r.status_code == 400


def test_un_descuento_grande_necesita_el_codigo_del_admin(cliente, datos, codigo_puesto):
    r = _vender(cliente, datos, descuento=3500, motivo_descuento="amigo del dueño")
    assert r.status_code == 403
    assert "código de un administrador" in r.json()["detail"]

    r = _vender(
        cliente,
        datos,
        descuento=3500,
        motivo_descuento="amigo del dueño",
        codigo_autorizacion="el-que-no-es",
    )
    assert r.status_code == 403
    assert "no es correcto" in r.json()["detail"]

    # Nada de lo rechazado quedó guardado.
    assert cliente.get("/api/ventas").json() == []

    r = _vender(
        cliente,
        datos,
        descuento=3500,
        motivo_descuento="amigo del dueño",
        codigo_autorizacion=CODIGO,
    )
    assert r.status_code == 201
    assert r.json()["total"] == 3500


def test_el_administrador_no_necesita_codigo_para_descontar(como, datos):
    r = _vender(como("admin"), datos, descuento=3500, motivo_descuento="invitación")
    assert r.status_code == 201


def test_una_cortesia_completa_descuenta_inventario_y_no_entra_plata(
    cliente, datos, codigo_puesto, ver_resumen
):
    r = _vender(
        cliente,
        datos,
        descuento=7000,
        motivo_descuento="la casa invita",
        codigo_autorizacion=CODIGO,
    )
    assert r.status_code == 201
    venta = r.json()
    assert venta["total"] == 0
    assert venta["pagos"] == []

    # Las cervezas sí salieron de la nevera.
    assert cliente.get(f"/api/productos/{datos['cerveza'].id}").json()["stock_actual"] == 98

    # Y regalarlas costó plata: la utilidad lo refleja.
    resumen = ver_resumen()
    assert resumen["total"] == 0
    assert resumen["utilidad"] == -4600
    assert _efectivo_esperado(cliente) == 0


def test_el_descuento_no_puede_pasar_la_cuenta(como, datos):
    r = _vender(como("admin"), datos, descuento=8000, motivo_descuento="error")
    assert r.status_code == 400


def test_el_dueno_ve_quien_hizo_cada_descuento_y_cada_anulacion(
    cliente, como, datos, codigo_puesto
):
    _vender(cliente, datos, descuento=500, motivo_descuento="redondeo")
    _vender(
        cliente,
        datos,
        descuento=7000,
        motivo_descuento="la casa invita",
        codigo_autorizacion=CODIGO,
    )
    ultima = _vender(cliente, datos).json()
    cliente.post(f"/api/ventas/{ultima['id']}/anular", json={"motivo": "se arrepintió"})

    novedades = como("admin").get("/api/reportes/novedades").json()

    descuentos = sorted(novedades["descuentos"], key=lambda n: n["monto"])
    assert [(d["monto"], d["motivo"], d["con_codigo"]) for d in descuentos] == [
        (500, "redondeo", False),
        (7000, "la casa invita", True),
    ]
    assert all(d["quien"] == "vendedor" for d in descuentos)

    assert len(novedades["anulaciones"]) == 1
    assert novedades["anulaciones"][0]["motivo"] == "se arrepintió"
    assert novedades["anulaciones"][0]["monto"] == 7000


# ------------------------------------------------- la mesa cambió al cobrar


def test_si_la_mesa_cambio_mientras_la_caja_miraba_no_se_cobra_a_ciegas(
    cliente, como, datos
):
    mesero = como("mesero")
    pedido = mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 4, "items": [{"producto_id": datos["cerveza"].id, "cantidad": 2}]},
    ).json()
    lo_que_vio_la_caja = pedido["total"]  # $7.000

    # Otra ronda mientras el cajero le lee la cuenta al cliente.
    mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 4, "items": [{"producto_id": datos["cerveza"].id, "cantidad": 3}]},
    )

    r = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar",
        json={"metodo_pago": "efectivo", "total_esperado": lo_que_vio_la_caja},
    )
    assert r.status_code == 409
    assert "$17.500" in r.json()["detail"]
    # La mesa sigue abierta para cobrarla bien.
    assert cliente.get(f"/api/pedidos/{pedido['id']}").json()["estado"] == "abierto"

    r = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar",
        json={"metodo_pago": "efectivo", "total_esperado": 17500},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 17500


# ------------------------------------------------- el mesero sin señal


def test_un_reintento_del_mismo_envio_no_duplica_el_pedido(como, datos):
    mesero = como("mesero")
    cuerpo = {
        "mesa": 5,
        "clave": "celular-1-envio-7",
        "items": [{"plato_id": datos["picada"].id, "cantidad": 1}],
    }
    primero = mesero.post("/api/pedidos/enviar", json=cuerpo)
    # Se cayó el WiFi antes de que llegara la respuesta: el celular reintenta.
    segundo = mesero.post("/api/pedidos/enviar", json=cuerpo)

    assert primero.status_code == 201
    assert segundo.status_code == 201
    pedido = segundo.json()
    assert pedido["id"] == primero.json()["id"]
    assert pedido["detalles"][0]["cantidad"] == 1
    assert pedido["total"] == 45000


def test_dos_envios_distintos_si_se_suman(como, datos):
    mesero = como("mesero")
    for clave in ("envio-a", "envio-b"):
        mesero.post(
            "/api/pedidos/enviar",
            json={
                "mesa": 5,
                "clave": clave,
                "items": [{"plato_id": datos["picada"].id, "cantidad": 1}],
            },
        )
    pedido = mesero.get("/api/pedidos/mesa/5").json()
    assert pedido["detalles"][0]["cantidad"] == 2


def test_un_envio_rechazado_no_gasta_su_clave(como, datos):
    """Si el servidor rechazó el pedido, la misma clave tiene que poder
    volver a entrar una vez corregido: nunca quedó registrado."""
    mesero = como("mesero")
    malo = mesero.post(
        "/api/pedidos/enviar",
        json={"mesa": 5, "clave": "envio-x", "items": [{"plato_id": 9999, "cantidad": 1}]},
    )
    assert malo.status_code == 404

    bueno = mesero.post(
        "/api/pedidos/enviar",
        json={
            "mesa": 5,
            "clave": "envio-x",
            "items": [{"plato_id": datos["picada"].id, "cantidad": 1}],
        },
    )
    assert bueno.status_code == 201
    assert bueno.json()["total"] == 45000
