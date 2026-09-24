"""La mesa se ocupa cuando el mesero sube el pedido, no cuando la toca.

El mesero anota en el celular y solo al confirmar sube todo junto. Estas
pruebas cubren esa frontera: qué pasa antes de subir, qué pasa al subir, y
que nunca quede una mesa ocupada sin nada dentro.
"""

from app import models


def mesa_libre(c, numero=5):
    return c.get(f"/api/pedidos/mesa/{numero}").json()


def enviar(c, numero, items):
    return c.post("/api/pedidos/enviar", json={"mesa": numero, "items": items})


# ------------------------------------------------- antes de subir el pedido


def test_una_mesa_sin_pedido_responde_vacia(como, datos):
    """Consultar una mesa libre no la abre ni es un error."""
    mesero = como("mesero")
    assert mesero.get("/api/pedidos/mesa/5").status_code == 200
    assert mesa_libre(mesero) is None


def test_consultar_una_mesa_no_la_ocupa(como, db, datos):
    mesero = como("mesero")
    mesero.get("/api/pedidos/mesa/5")
    mesero.get("/api/pedidos/mesa/5")

    assert db.query(models.PedidoMesa).count() == 0
    assert mesero.get("/api/pedidos").json() == []


# ----------------------------------------------------- al subir el pedido


def test_subir_el_pedido_ocupa_la_mesa(como, datos):
    mesero = como("mesero")
    respuesta = enviar(mesero, 5, [{"plato_id": datos["picada"].id, "cantidad": 2}])

    assert respuesta.status_code == 201
    pedido = respuesta.json()
    assert pedido["mesa"] == 5
    assert pedido["estado"] == "abierto"
    assert len(pedido["detalles"]) == 1
    assert pedido["detalles"][0]["cantidad"] == 2


def test_el_pedido_sube_con_varios_items_de_una_vez(como, datos):
    mesero = como("mesero")
    respuesta = enviar(
        mesero,
        5,
        [
            {"plato_id": datos["picada"].id, "cantidad": 1},
            {"producto_id": datos["cerveza"].id, "cantidad": 3},
        ],
    )

    pedido = respuesta.json()
    assert len(pedido["detalles"]) == 2
    assert pedido["total"] == 45000 + 3 * 3500


def test_la_mesa_aparece_ocupada_despues_de_subir(como, datos):
    mesero = como("mesero")
    enviar(mesero, 5, [{"plato_id": datos["picada"].id, "cantidad": 1}])

    abiertas = mesero.get("/api/pedidos").json()
    assert [p["mesa"] for p in abiertas] == [5]


def test_subir_otra_vez_suma_a_la_misma_mesa(como, datos):
    """La segunda ronda no abre otra mesa: se acumula en la que ya está."""
    mesero = como("mesero")
    enviar(mesero, 5, [{"plato_id": datos["picada"].id, "cantidad": 1}])
    segunda = enviar(mesero, 5, [{"producto_id": datos["cerveza"].id, "cantidad": 2}])

    assert segunda.status_code == 201
    pedido = segunda.json()
    assert len(pedido["detalles"]) == 2
    assert len(mesero.get("/api/pedidos").json()) == 1


def test_pedir_lo_mismo_otra_vez_suma_cantidad(como, datos):
    mesero = como("mesero")
    enviar(mesero, 5, [{"producto_id": datos["cerveza"].id, "cantidad": 2}])
    segunda = enviar(mesero, 5, [{"producto_id": datos["cerveza"].id, "cantidad": 3}])

    detalles = segunda.json()["detalles"]
    assert len(detalles) == 1
    assert detalles[0]["cantidad"] == 5


def test_las_notas_distintas_van_en_lineas_distintas(como, datos):
    mesero = como("mesero")
    respuesta = enviar(
        mesero,
        5,
        [
            {"plato_id": datos["picada"].id, "cantidad": 1, "notas": "sin ensalada"},
            {"plato_id": datos["picada"].id, "cantidad": 1, "notas": "con extra queso"},
        ],
    )
    assert len(respuesta.json()["detalles"]) == 2


# -------------------------------------------------------- lo que se rechaza


def test_un_pedido_vacio_no_ocupa_la_mesa(como, db, datos):
    """El caso que dejaba mesas ocupadas y vacías."""
    mesero = como("mesero")
    respuesta = enviar(mesero, 5, [])

    assert respuesta.status_code == 400
    assert db.query(models.PedidoMesa).count() == 0


def test_un_producto_inexistente_no_deja_la_mesa_a_medias(como, db, datos):
    """Si un ítem falla, no queda ni la mesa abierta ni los otros ítems."""
    mesero = como("mesero")
    respuesta = enviar(
        mesero,
        5,
        [
            {"plato_id": datos["picada"].id, "cantidad": 1},
            {"producto_id": 99999, "cantidad": 1},
        ],
    )

    assert respuesta.status_code == 404
    assert db.query(models.PedidoMesa).count() == 0
    assert db.query(models.DetallePedidoMesa).count() == 0


def test_el_vendedor_tambien_puede_subir_pedidos(cliente, datos):
    """El vendedor cubre el salón cuando hace falta."""
    assert enviar(cliente, 5, [{"plato_id": datos["picada"].id, "cantidad": 1}]).status_code == 201


def test_sin_sesion_no_se_sube_nada(db, datos):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        anonimo = TestClient(app)
        respuesta = anonimo.post(
            "/api/pedidos/enviar", json={"mesa": 5, "items": [{"plato_id": 1, "cantidad": 1}]}
        )
        assert respuesta.status_code == 401
        assert db.query(models.PedidoMesa).count() == 0
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------ sigue el resto igual


def test_despues_de_subir_se_puede_pedir_la_cuenta(como, datos):
    mesero = como("mesero")
    pedido = enviar(mesero, 5, [{"plato_id": datos["picada"].id, "cantidad": 1}]).json()

    respuesta = mesero.post(f"/api/pedidos/{pedido['id']}/pedir-cuenta")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "cuenta_pedida"


def test_una_mesa_cobrada_deja_de_aparecer_y_se_puede_volver_a_abrir(como, datos):
    mesero = como("mesero")
    vendedor_admin = como("admin")
    pedido = enviar(mesero, 5, [{"plato_id": datos["picada"].id, "cantidad": 1}]).json()

    vendedor_admin.post(
        f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"}
    )

    assert mesa_libre(mesero) is None
    nueva = enviar(mesero, 5, [{"producto_id": datos["cerveza"].id, "cantidad": 1}])
    assert nueva.status_code == 201
    assert nueva.json()["id"] != pedido["id"]
