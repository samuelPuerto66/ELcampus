"""Platos para llevar vendidos en la caja: se cobran de una y van a la cocina."""


def _vender_para_llevar(cliente, datos, nombre="Juan", **extra):
    return cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "nombre_para_llevar": nombre,
            "items": [
                {"plato_id": datos["picada"].id, "cantidad": 2},
                {"producto_id": datos["cerveza"].id, "cantidad": 1},
            ],
            **extra,
        },
    )


def test_un_plato_vendido_en_la_caja_le_llega_a_la_cocina(cliente, como, datos):
    r = _vender_para_llevar(cliente, datos)
    assert r.status_code == 201
    assert r.json()["total"] == 93500

    comanda = como("cocina").get("/api/cocina/pendientes").json()
    # Solo la picada: la cerveza se entrega en la caja.
    assert len(comanda) == 1
    assert comanda[0]["nombre"] == "Picada"
    assert comanda[0]["cantidad"] == 2
    assert comanda[0]["para_llevar"] is True
    assert comanda[0]["nombre_cliente"] == "Juan"


def test_sin_platos_no_hay_comanda(cliente, como, datos):
    cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": datos["cerveza"].id, "cantidad": 1}],
        },
    )
    assert como("cocina").get("/api/cocina/pendientes").json() == []


def test_el_nombre_es_opcional(cliente, como, datos):
    _vender_para_llevar(cliente, datos, nombre="  ")
    comanda = como("cocina").get("/api/cocina/pendientes").json()
    assert comanda[0]["nombre_cliente"] is None


def test_cuando_la_cocina_lo_marca_listo_sale_de_la_lista(cliente, como, datos):
    _vender_para_llevar(cliente, datos)
    cocina = como("cocina")
    item = cocina.get("/api/cocina/pendientes").json()[0]

    cocina.post(f"/api/cocina/items/{item['id']}/listo")

    assert cocina.get("/api/cocina/pendientes").json() == []


def test_si_se_anula_la_venta_la_cocina_ya_no_lo_prepara(cliente, como, datos):
    venta = _vender_para_llevar(cliente, datos).json()
    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "se fue"})

    assert como("cocina").get("/api/cocina/pendientes").json() == []


def test_un_pedido_para_llevar_no_ocupa_ninguna_mesa(cliente, como, datos):
    _vender_para_llevar(cliente, datos)
    mesero = como("mesero")
    assert mesero.get("/api/pedidos").json() == []
    assert mesero.get("/api/pedidos/mesa/0").json() is None


def test_conviven_las_mesas_y_lo_para_llevar(cliente, como, datos):
    como("mesero").post(
        "/api/pedidos/enviar",
        json={"mesa": 5, "items": [{"plato_id": datos["picada"].id, "cantidad": 1}]},
    )
    _vender_para_llevar(cliente, datos)

    comanda = como("cocina").get("/api/cocina/pendientes").json()
    assert sorted((c["para_llevar"], c["mesa"]) for c in comanda) == [(False, 5), (True, 0)]
