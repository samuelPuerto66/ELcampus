"""Recetas: vender un plato descuenta sus insumos y su costo deja de ser
un estimado."""

import pytest

from app import models


@pytest.fixture
def carne(db):
    """Un insumo: se controla en inventario pero no se vende suelto."""
    producto = models.Producto(
        codigo_barras="INS-CARNE",
        nombre="Carne de res",
        precio=0,
        tipo_venta=models.TipoVenta.peso,
        precio_por_kg=0,
        costo=28000,
        stock_actual=10,
        es_insumo=True,
    )
    db.add(producto)
    db.commit()
    return producto


@pytest.fixture
def chorizo(db):
    producto = models.Producto(
        codigo_barras="INS-CHORIZO",
        nombre="Chorizo",
        precio=0,
        costo=2000,
        stock_actual=50,
        es_insumo=True,
    )
    db.add(producto)
    db.commit()
    return producto


def _poner_receta(admin, plato_id, insumos):
    return admin.put(f"/api/platos/{plato_id}/receta", json=insumos)


def _cobrar_plato(cliente, plato_id, cantidad=1):
    return cliente.post(
        "/api/ventas",
        json={
            "tipo": "restaurante",
            "metodo_pago": "efectivo",
            "mesa": 1,
            "items": [{"plato_id": plato_id, "cantidad": cantidad}],
        },
    ).json()


def test_guardar_una_receta_calcula_el_costo_del_plato(como, datos, carne, chorizo):
    admin = como("admin")

    receta = _poner_receta(
        admin,
        datos["picada"].id,
        [
            {"producto_id": carne.id, "cantidad": 0.4},
            {"producto_id": chorizo.id, "cantidad": 2},
        ],
    ).json()

    # 0,4 kg × 28.000 = 11.200  +  2 × 2.000 = 4.000  →  15.200
    assert receta["costo"] == 15200
    assert receta["utilidad"] == 29800  # la picada se vende a 45.000
    assert [i["nombre"] for i in receta["insumos"]] == ["Carne de res", "Chorizo"]


def test_vender_el_plato_descuenta_la_carne_y_el_chorizo(
    cliente, como, datos, carne, chorizo
):
    _poner_receta(
        como("admin"),
        datos["picada"].id,
        [
            {"producto_id": carne.id, "cantidad": 0.4},
            {"producto_id": chorizo.id, "cantidad": 2},
        ],
    )

    _cobrar_plato(cliente, datos["picada"].id, cantidad=2)

    # Dos picadas: 0,8 kg de carne y 4 chorizos.
    assert carne.stock_actual == pytest.approx(9.2)
    assert chorizo.stock_actual == 46


def test_la_utilidad_del_dia_usa_el_costo_de_la_receta(
    cliente, como, datos, carne, chorizo
):
    _poner_receta(
        como("admin"),
        datos["picada"].id,
        [
            {"producto_id": carne.id, "cantidad": 0.4},
            {"producto_id": chorizo.id, "cantidad": 2},
        ],
    )

    _cobrar_plato(cliente, datos["picada"].id)
    resumen = cliente.get("/api/reportes/dia").json()

    assert resumen["total"] == 45000
    assert resumen["costo"] == 15200
    assert resumen["utilidad"] == 29800
    assert resumen["lineas_sin_costo"] == 0


def test_si_a_un_insumo_le_falta_el_costo_la_receta_lo_dice(como, datos, carne, db):
    sin_costo = models.Producto(
        codigo_barras="INS-PAPA", nombre="Papa", precio=0, stock_actual=20, es_insumo=True
    )
    db.add(sin_costo)
    db.commit()

    receta = _poner_receta(
        como("admin"),
        datos["picada"].id,
        [
            {"producto_id": carne.id, "cantidad": 0.4},
            {"producto_id": sin_costo.id, "cantidad": 1},
        ],
    ).json()

    # Prefiere decir "no sé" antes que inventar un costo a medias.
    assert receta["costo"] is None
    assert receta["utilidad"] is None


def test_anular_devuelve_los_insumos_al_inventario(cliente, como, datos, carne, chorizo):
    _poner_receta(
        como("admin"),
        datos["picada"].id,
        [
            {"producto_id": carne.id, "cantidad": 0.4},
            {"producto_id": chorizo.id, "cantidad": 2},
        ],
    )
    venta = _cobrar_plato(cliente, datos["picada"].id)

    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "se devolvió"})

    assert carne.stock_actual == pytest.approx(10)
    assert chorizo.stock_actual == 50


def test_anular_devuelve_lo_que_salio_aunque_la_receta_haya_cambiado(
    cliente, como, datos, carne, chorizo
):
    """Si se devolviera según la receta de hoy, un cambio de receta dejaría
    el inventario descuadrado para siempre."""
    admin = como("admin")
    _poner_receta(admin, datos["picada"].id, [{"producto_id": carne.id, "cantidad": 0.4}])
    venta = _cobrar_plato(cliente, datos["picada"].id)
    assert carne.stock_actual == pytest.approx(9.6)

    # Cambia la receta después de haber vendido.
    _poner_receta(
        admin, datos["picada"].id, [{"producto_id": chorizo.id, "cantidad": 5}]
    )

    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "devolución"})

    # Se devuelve la carne que de verdad salió, no los chorizos de ahora.
    assert carne.stock_actual == pytest.approx(10)
    assert chorizo.stock_actual == 50


def test_un_insumo_no_aparece_en_la_lista_de_lo_que_se_vende(cliente, datos, carne):
    nombres = [p["nombre"] for p in cliente.get("/api/productos").json()]

    assert "Carne de res" not in nombres
    assert "Cerveza Aguila 330ml" in nombres


def test_el_administrador_sí_ve_los_insumos_para_manejarlos(como, datos, carne):
    nombres = [
        p["nombre"]
        for p in como("admin").get("/api/productos?incluir_insumos=true").json()
    ]

    assert "Carne de res" in nombres


def test_escanear_un_insumo_en_la_caja_avisa_que_no_se_vende(cliente, carne):
    respuesta = cliente.get("/api/productos/codigo/INS-CARNE")

    assert respuesta.status_code == 409
    assert "insumo" in respuesta.json()["detail"]


def test_tampoco_se_puede_cobrar_un_insumo_por_la_api(cliente, carne):
    respuesta = cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": carne.id, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 409


def test_quitar_la_receta_vuelve_al_costo_escrito_a_mano(como, datos, carne):
    admin = como("admin")
    admin.patch(f"/api/platos/{datos['picada'].id}", json={"costo": 18000})
    _poner_receta(admin, datos["picada"].id, [{"producto_id": carne.id, "cantidad": 0.4}])
    assert admin.get(f"/api/platos/{datos['picada'].id}/receta").json()["costo"] == 11200

    _poner_receta(admin, datos["picada"].id, [])

    assert admin.get(f"/api/platos/{datos['picada'].id}/receta").json()["costo"] == 18000


def test_no_se_puede_repetir_un_insumo_en_la_receta(como, datos, carne):
    respuesta = _poner_receta(
        como("admin"),
        datos["picada"].id,
        [
            {"producto_id": carne.id, "cantidad": 0.4},
            {"producto_id": carne.id, "cantidad": 0.2},
        ],
    )

    assert respuesta.status_code == 400
    assert "dos veces" in respuesta.json()["detail"]


def test_solo_el_administrador_cambia_recetas(cliente, datos, carne):
    respuesta = _poner_receta(
        cliente, datos["picada"].id, [{"producto_id": carne.id, "cantidad": 0.4}]
    )

    assert respuesta.status_code == 403
