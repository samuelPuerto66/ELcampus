import pytest


@pytest.fixture
def mesero(como):
    return como("mesero")


def _abrir(mesero, mesa=7):
    return mesero.post("/api/pedidos", json={"mesa": mesa}).json()


def test_abrir_mesa_y_agregar_lo_que_pide_el_cliente(mesero, datos):
    pedido = _abrir(mesero)
    assert pedido["estado"] == "abierto"
    assert pedido["total"] == 0

    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"plato_id": datos["picada"].id, "cantidad": 1},
    )
    respuesta = mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"producto_id": datos["cerveza"].id, "cantidad": 2},
    )

    actualizado = respuesta.json()
    assert actualizado["total"] == 52000
    assert len(actualizado["detalles"]) == 2


def test_pedir_lo_mismo_otra_vez_suma_en_la_misma_linea(mesero, datos):
    pedido = _abrir(mesero)
    cuerpo = {"producto_id": datos["cerveza"].id, "cantidad": 1}

    mesero.post(f"/api/pedidos/{pedido['id']}/items", json=cuerpo)
    respuesta = mesero.post(f"/api/pedidos/{pedido['id']}/items", json=cuerpo)

    actualizado = respuesta.json()
    assert len(actualizado["detalles"]) == 1
    assert actualizado["detalles"][0]["cantidad"] == 2


def test_una_nota_distinta_abre_una_linea_aparte(mesero, datos):
    pedido = _abrir(mesero)

    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"plato_id": datos["picada"].id, "cantidad": 1},
    )
    respuesta = mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"plato_id": datos["picada"].id, "cantidad": 1, "notas": "sin chorizo"},
    )

    assert len(respuesta.json()["detalles"]) == 2


def test_no_se_puede_abrir_dos_veces_la_misma_mesa(mesero):
    _abrir(mesero, mesa=3)
    segunda = mesero.post("/api/pedidos", json={"mesa": 3})

    assert segunda.status_code == 409


def test_quitar_todo_lo_de_una_linea_la_borra(mesero, datos):
    pedido = _abrir(mesero)
    con_item = mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"producto_id": datos["cerveza"].id, "cantidad": 2},
    ).json()
    detalle_id = con_item["detalles"][0]["id"]

    respuesta = mesero.post(
        f"/api/pedidos/{pedido['id']}/items/{detalle_id}/quitar",
        json={"cantidad": 2, "motivo": "se anotó en la mesa equivocada"},
    )

    assert respuesta.json()["detalles"] == []


def test_no_se_puede_pedir_la_cuenta_de_una_mesa_vacia(mesero):
    pedido = _abrir(mesero)
    respuesta = mesero.post(f"/api/pedidos/{pedido['id']}/pedir-cuenta")

    assert respuesta.status_code == 400


def test_el_camino_completo_de_una_mesa(mesero, cliente, datos):
    pedido = _abrir(mesero, mesa=7)
    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"plato_id": datos["picada"].id, "cantidad": 1},
    )
    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"producto_id": datos["cerveza"].id, "cantidad": 2},
    )

    pidio = mesero.post(f"/api/pedidos/{pedido['id']}/pedir-cuenta").json()
    assert pidio["estado"] == "cuenta_pedida"
    assert pidio["hora_cuenta_pedida"] is not None

    cobro = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "nequi"}
    )

    assert cobro.status_code == 200
    venta = cobro.json()
    assert venta["total"] == 52000
    assert venta["mesa"] == 7
    assert venta["metodo_pago"] == "nequi"
    # La cerveza salió del inventario; la picada no toca stock.
    assert datos["cerveza"].stock_actual == 98

    ya_cobrada = mesero.get(f"/api/pedidos/{pedido['id']}").json()
    assert ya_cobrada["estado"] == "pagado"
    assert ya_cobrada["venta_id"] == venta["id"]


def test_una_mesa_cobrada_no_recibe_mas_pedidos(mesero, cliente, datos):
    pedido = _abrir(mesero)
    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"producto_id": datos["cerveza"].id, "cantidad": 1},
    )
    cliente.post(f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"})

    respuesta = mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"producto_id": datos["cerveza"].id, "cantidad": 1},
    )

    assert respuesta.status_code == 409


def test_el_mesero_no_puede_cobrar_la_mesa(mesero, datos):
    pedido = _abrir(mesero)
    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"producto_id": datos["cerveza"].id, "cantidad": 1},
    )

    respuesta = mesero.post(
        f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"}
    )

    assert respuesta.status_code == 403
