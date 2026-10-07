"""Fallos encontrados revisando el sistema antes de la temporada.

Cada prueba es un caso que antes rompía algo o dejaba un dato falso.
"""

from app import models


def test_las_mesas_atendidas_cuentan_cada_grupo(cliente, como, datos, ver_resumen):
    mesero = como("mesero")
    # La mesa 2 se llenó tres veces en la noche.
    for _ in range(3):
        pedido = mesero.post(
            "/api/pedidos/enviar",
            json={"mesa": 2, "items": [{"producto_id": datos["cerveza"].id, "cantidad": 1}]},
        ).json()
        cliente.post(f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"})

    # Una venta de mostrador no es una mesa.
    cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": datos["cerveza"].id, "cantidad": 1}],
        },
    )

    assert ver_resumen()["mesas_atendidas"] == 3


def test_el_mesero_y_la_cocina_no_ven_cuanto_gana_el_negocio(como):
    for rol in ("mesero", "cocina", "vendedor"):
        c = como(rol)
        assert c.get("/api/reportes/dia").status_code == 403
        assert c.get("/api/reportes/novedades").status_code == 403

    assert como("mesero").get("/api/ventas").status_code == 403
    assert como("cocina").get("/api/ventas").status_code == 403


def test_un_insumo_no_puede_entrar_a_una_mesa(como, datos, db):
    """Antes entraba, y después la caja no podía cobrar esa mesa."""
    carne = models.Producto(
        codigo_barras="CARNE", nombre="Carne de res", precio=1, stock_actual=5, es_insumo=True
    )
    db.add(carne)
    db.commit()

    r = como("mesero").post(
        "/api/pedidos/enviar",
        json={"mesa": 9, "items": [{"producto_id": carne.id, "cantidad": 1}]},
    )
    assert r.status_code == 409
    assert "insumo" in r.json()["detail"]
    # Y la mesa no quedó ocupada a medias.
    assert como("mesero").get("/api/pedidos/mesa/9").json() is None


def test_borrar_un_plato_que_una_mesa_esta_esperando_avisa_en_vez_de_romper(como, datos):
    como("mesero").post(
        "/api/pedidos/enviar",
        json={"mesa": 6, "items": [{"plato_id": datos["picada"].id, "cantidad": 1}]},
    )
    r = como("admin").delete(f"/api/platos/{datos['picada'].id}")
    assert r.status_code == 409
    assert "todavía no ha pagado" in r.json()["detail"]


def test_no_se_registra_un_producto_con_precio_negativo(como):
    r = como("admin").post(
        "/api/productos", json={"codigo_barras": "X1", "nombre": "Algo", "precio": -500}
    )
    assert r.status_code == 422


def test_un_producto_por_peso_sin_precio_por_kilo_avisa_en_vez_de_romper(como):
    r = como("admin").post(
        "/api/productos",
        json={"codigo_barras": "X2", "nombre": "Queso", "precio": 0, "tipo_venta": "peso"},
    )
    assert r.status_code == 422


def test_no_se_abre_la_caja_con_plata_negativa(como):
    c = como("vendedor")
    c.post("/api/caja/cerrar", json={"efectivo_contado": 0})
    assert c.post("/api/caja/abrir", json={"base_inicial": -1000}).status_code == 422


def test_el_historial_de_caja_dice_quien_abrio_cada_turno(como):
    c = como("vendedor")
    c.post("/api/caja/cerrar", json={"efectivo_contado": 0})
    historial = como("admin").get("/api/caja").json()
    assert historial[0]["usuario_nombre"] == "vendedor"
