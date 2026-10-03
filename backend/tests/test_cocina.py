"""La cocina tiene que enterarse de los platos cuando el mesero los pide,
no cuando el cliente pide la cuenta."""

import pytest


@pytest.fixture
def mesero(como):
    return como("mesero")


@pytest.fixture
def cocinero(como):
    return como("cocina")


def _pedir(mesero, mesa, items):
    return mesero.post("/api/pedidos/enviar", json={"mesa": mesa, "items": items}).json()


def test_un_plato_pedido_aparece_de_una_en_la_cocina(mesero, cocinero, datos):
    _pedir(mesero, 4, [{"plato_id": datos["picada"].id, "cantidad": 2}])

    comanda = cocinero.get("/api/cocina/pendientes").json()

    assert len(comanda) == 1
    assert comanda[0]["mesa"] == 4
    assert comanda[0]["nombre"] == "Picada"
    assert comanda[0]["cantidad"] == 2
    assert comanda[0]["estado_cocina"] == "pendiente"


def test_las_bebidas_no_van_a_la_cocina(mesero, cocinero, datos):
    _pedir(
        mesero,
        4,
        [
            {"producto_id": datos["cerveza"].id, "cantidad": 3},
            {"plato_id": datos["picada"].id, "cantidad": 1},
        ],
    )

    comanda = cocinero.get("/api/cocina/pendientes").json()

    # Solo la picada: una cerveza no se cocina.
    assert [i["nombre"] for i in comanda] == ["Picada"]


def test_marcar_listo_lo_saca_de_la_cola(mesero, cocinero, datos):
    _pedir(mesero, 7, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    item = cocinero.get("/api/cocina/pendientes").json()[0]

    respuesta = cocinero.post(f"/api/cocina/items/{item['id']}/listo")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado_cocina"] == "listo"
    assert cocinero.get("/api/cocina/pendientes").json() == []
    # Pero sigue estando en la comanda completa.
    assert len(cocinero.get("/api/cocina/pendientes?incluir_listos=true").json()) == 1


def test_se_puede_deshacer_si_se_marco_el_plato_equivocado(mesero, cocinero, datos):
    _pedir(mesero, 7, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    item = cocinero.get("/api/cocina/pendientes").json()[0]
    cocinero.post(f"/api/cocina/items/{item['id']}/listo")

    cocinero.post(f"/api/cocina/items/{item['id']}/deshacer")

    assert len(cocinero.get("/api/cocina/pendientes").json()) == 1


def test_pedir_otro_plato_igual_despues_de_listo_crea_una_linea_nueva(
    mesero, cocinero, datos
):
    """Si se sumara a la línea ya despachada, el segundo plato quedaría
    escondido detrás de un 'listo' y nadie lo prepararía."""
    pedido = _pedir(mesero, 9, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    primera = cocinero.get("/api/cocina/pendientes").json()[0]
    cocinero.post(f"/api/cocina/items/{primera['id']}/listo")

    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"plato_id": datos["picada"].id, "cantidad": 1},
    )

    pendientes = cocinero.get("/api/cocina/pendientes").json()
    assert len(pendientes) == 1
    assert pendientes[0]["id"] != primera["id"]


def test_pedir_mas_de_algo_que_sigue_pendiente_sí_suma(mesero, cocinero, datos):
    pedido = _pedir(mesero, 9, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    mesero.post(
        f"/api/pedidos/{pedido['id']}/items",
        json={"plato_id": datos["picada"].id, "cantidad": 1},
    )

    pendientes = cocinero.get("/api/cocina/pendientes").json()

    assert len(pendientes) == 1
    assert pendientes[0]["cantidad"] == 2


def test_una_mesa_cobrada_desaparece_de_la_cocina(mesero, cocinero, cliente, datos):
    pedido = _pedir(mesero, 2, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    assert len(cocinero.get("/api/cocina/pendientes").json()) == 1

    cliente.post(f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"})

    assert cocinero.get("/api/cocina/pendientes").json() == []


def test_la_comanda_llega_en_orden_de_llegada(mesero, cocinero, datos):
    _pedir(mesero, 1, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    _pedir(mesero, 2, [{"plato_id": datos["picada"].id, "cantidad": 1}])

    comanda = cocinero.get("/api/cocina/pendientes").json()

    assert [i["mesa"] for i in comanda] == [1, 2]


def test_la_cocina_no_puede_cobrar(cocinero, datos):
    respuesta = cocinero.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": datos["cerveza"].id, "cantidad": 1}],
        },
    )

    assert respuesta.status_code == 403


def test_la_cocina_no_puede_tocar_precios(cocinero, datos):
    respuesta = cocinero.patch(
        f"/api/productos/{datos['cerveza'].id}", json={"precio": 1}
    )

    assert respuesta.status_code == 403
