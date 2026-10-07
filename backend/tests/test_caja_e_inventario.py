import pytest


def _cobrar_efectivo(cliente, producto_id, cantidad):
    return cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": producto_id, "cantidad": cantidad}],
        },
    ).json()


@pytest.mark.sin_caja
def test_cierre_de_caja_cuadra_con_lo_vendido_en_efectivo(cliente, datos):
    cliente.post("/api/caja/abrir", json={"base_inicial": 100000})
    _cobrar_efectivo(cliente, datos["cerveza"].id, 3)  # 10.500

    cierre = cliente.post("/api/caja/cerrar", json={"efectivo_contado": 110500}).json()

    assert cierre["efectivo_esperado"] == 110500
    assert cierre["diferencia"] == 0
    assert cierre["estado"] == "cerrado"


@pytest.mark.sin_caja
def test_un_faltante_queda_registrado_tal_cual(cliente, datos):
    cliente.post("/api/caja/abrir", json={"base_inicial": 100000})
    _cobrar_efectivo(cliente, datos["cerveza"].id, 2)  # 7.000

    cierre = cliente.post("/api/caja/cerrar", json={"efectivo_contado": 105000}).json()

    assert cierre["efectivo_esperado"] == 107000
    assert cierre["diferencia"] == -2000


@pytest.mark.sin_caja
def test_las_ventas_por_nequi_no_entran_al_cuadre_de_efectivo(cliente, datos):
    cliente.post("/api/caja/abrir", json={"base_inicial": 50000})
    cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "nequi",
            "items": [{"producto_id": datos["cerveza"].id, "cantidad": 4}],
        },
    )

    cierre = cliente.post("/api/caja/cerrar", json={"efectivo_contado": 50000}).json()

    assert cierre["efectivo_esperado"] == 50000
    assert cierre["diferencia"] == 0


@pytest.mark.sin_caja
def test_no_se_abren_dos_cajas_al_tiempo(cliente):
    cliente.post("/api/caja/abrir", json={"base_inicial": 50000})
    segunda = cliente.post("/api/caja/abrir", json={"base_inicial": 50000})

    assert segunda.status_code == 409


def test_la_mercancia_que_llega_suma_al_stock(cliente, datos):
    respuesta = cliente.post(
        "/api/inventario/entrada",
        json={"producto_id": datos["cerveza"].id, "cantidad": 24},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["stock_actual"] == 124


def test_el_ajuste_de_conteo_fija_el_numero_exacto(como, datos):
    admin = como("admin")
    respuesta = admin.post(
        "/api/inventario/ajuste",
        json={
            "producto_id": datos["cerveza"].id,
            "stock_real": 88,
            "motivo": "conteo del lunes",
        },
    )

    assert respuesta.json()["stock_actual"] == 88


def test_alerta_de_lo_que_se_esta_acabando(cliente, como, datos):
    como("admin").post(
        "/api/inventario/ajuste",
        json={"producto_id": datos["cerveza"].id, "stock_real": 2, "motivo": "conteo"},
    )

    alertas = cliente.get("/api/inventario/alertas").json()
    nombres = [p["nombre"] for p in alertas]

    assert "Cerveza Aguila 330ml" in nombres


def test_resumen_del_dia(cliente, datos, ver_resumen):
    _cobrar_efectivo(cliente, datos["cerveza"].id, 2)  # 7.000
    cliente.post(
        "/api/ventas",
        json={
            "tipo": "restaurante",
            "metodo_pago": "nequi",
            "mesa": 4,
            "items": [{"plato_id": datos["picada"].id, "cantidad": 1}],
        },
    )

    resumen = ver_resumen()

    assert resumen["total"] == 52000
    assert resumen["cantidad_ventas"] == 2
    assert resumen["ticket_promedio"] == 26000
    assert {m["metodo_pago"] for m in resumen["por_metodo"]} == {"efectivo", "nequi"}
    assert resumen["mas_vendidos"][0]["nombre"] == "Cerveza Aguila 330ml"


def test_una_venta_anulada_no_cuenta_en_el_reporte(cliente, datos, ver_resumen):
    venta = _cobrar_efectivo(cliente, datos["cerveza"].id, 2)
    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "prueba"})

    resumen = ver_resumen()

    assert resumen["total"] == 0
    assert resumen["cantidad_ventas"] == 0
