"""Notas para la cocina y corregir lo que ya se envió a una mesa.

Corregir es quitar plata de una cuenta, así que tiene las mismas reglas que
anular una venta: lo propio y reciente se arregla solo; lo demás necesita
el código de un administrador, y todo queda escrito.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import config, models
from app.auth import crear_token
from app.main import app
from app.security import hash_password

CODIGO = "brasa-2026"


@pytest.fixture
def codigo_puesto(tmp_path, monkeypatch):
    archivo = tmp_path / ".codigo-admin"
    archivo.write_text(hash_password(CODIGO), encoding="utf-8")
    monkeypatch.setattr(config, "ARCHIVO_CODIGO_ADMIN", archivo)


@pytest.fixture
def otro_mesero(db, como):
    """Un segundo mesero, para probar lo que no es propio."""
    usuario = models.Usuario(
        nombre="mesero2",
        rol=models.RolUsuario.mesero,
        password_hash=hash_password("clave-de-prueba"),
    )
    db.add(usuario)
    db.commit()
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {crear_token(usuario)}"
    return c


def _enviar(c, mesa, *items):
    return c.post("/api/pedidos/enviar", json={"mesa": mesa, "items": list(items)}).json()


def _quitar(c, pedido, detalle, cantidad=1, motivo="se anotó de más", **extra):
    return c.post(
        f"/api/pedidos/{pedido['id']}/items/{detalle['id']}/quitar",
        json={"cantidad": cantidad, "motivo": motivo, **extra},
    )


def _envejecer(db, detalle_id, minutos):
    detalle = db.get(models.DetallePedidoMesa, detalle_id)
    detalle.actualizado_en = datetime.now() - timedelta(minutes=minutos)
    db.commit()


# ------------------------------------------------------------------ notas


def test_la_nota_llega_a_la_cocina(como, datos):
    _enviar(
        como("mesero"),
        3,
        {"plato_id": datos["picada"].id, "cantidad": 1, "notas": "sin cebolla"},
    )
    comanda = como("cocina").get("/api/cocina/pendientes").json()
    assert comanda[0]["notas"] == "sin cebolla"


def test_una_nota_en_blanco_es_lo_mismo_que_no_tener_nota(como, datos):
    mesero = como("mesero")
    _enviar(mesero, 3, {"plato_id": datos["picada"].id, "cantidad": 1})
    pedido = _enviar(
        mesero, 3, {"plato_id": datos["picada"].id, "cantidad": 1, "notas": "   "}
    )
    # Se sumó a la línea que ya había en vez de abrir una con nota vacía.
    assert len(pedido["detalles"]) == 1
    assert pedido["detalles"][0]["cantidad"] == 2
    assert pedido["detalles"][0]["notas"] is None


def test_dos_picadas_una_sin_cebolla(como, datos):
    pedido = _enviar(
        como("mesero"),
        3,
        {"plato_id": datos["picada"].id, "cantidad": 1},
        {"plato_id": datos["picada"].id, "cantidad": 1, "notas": "sin cebolla"},
    )
    notas = sorted((d["notas"] or "") for d in pedido["detalles"])
    assert notas == ["", "sin cebolla"]


def test_una_nota_demasiado_larga_se_rechaza(como, datos):
    r = como("mesero").post(
        "/api/pedidos/enviar",
        json={
            "mesa": 3,
            "items": [{"plato_id": datos["picada"].id, "cantidad": 1, "notas": "x" * 121}],
        },
    )
    assert r.status_code == 422


# ------------------------------------------------- corregir lo propio


def test_el_mesero_corrige_solo_lo_que_acaba_de_enviar(como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 3})

    r = _quitar(mesero, pedido, pedido["detalles"][0], cantidad=1)

    assert r.status_code == 200
    assert r.json()["detalles"][0]["cantidad"] == 2
    assert r.json()["total"] == 7000


def test_no_se_puede_quitar_mas_de_lo_que_hay(como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    r = _quitar(mesero, pedido, pedido["detalles"][0], cantidad=3)
    assert r.status_code == 400
    assert "solo hay 2" in r.json()["detail"]


def test_toda_correccion_lleva_motivo(como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    assert _quitar(mesero, pedido, pedido["detalles"][0], motivo="  ").status_code == 422


def test_ya_no_hay_forma_de_cambiar_cantidades_sin_dejar_rastro(como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    detalle = pedido["detalles"][0]
    r = mesero.patch(
        f"/api/pedidos/{pedido['id']}/items/{detalle['id']}", json={"cantidad": 0}
    )
    assert r.status_code == 405


# ------------------------------------------- lo que necesita al administrador


def test_lo_que_envio_otro_mesero_necesita_el_codigo(como, otro_mesero, datos, codigo_puesto):
    pedido = _enviar(como("mesero"), 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    detalle = pedido["detalles"][0]

    r = _quitar(otro_mesero, pedido, detalle)
    assert r.status_code == 403
    assert "envió otra persona" in r.json()["detail"]

    r = _quitar(otro_mesero, pedido, detalle, codigo_autorizacion=CODIGO)
    assert r.status_code == 200


def test_pasados_unos_minutos_tambien_necesita_el_codigo(como, db, datos, codigo_puesto):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    detalle = pedido["detalles"][0]
    _envejecer(db, detalle["id"], minutos=config.MINUTOS_PARA_CORREGIR + 1)

    r = _quitar(mesero, pedido, detalle)
    assert r.status_code == 403
    assert "más de 5 minutos" in r.json()["detail"]

    r = _quitar(mesero, pedido, detalle, codigo_autorizacion="el-que-no-es")
    assert r.status_code == 403
    assert "no es correcto" in r.json()["detail"]


def test_un_plato_que_la_cocina_ya_hizo_necesita_el_codigo(como, datos, codigo_puesto):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"plato_id": datos["picada"].id, "cantidad": 1})
    detalle = pedido["detalles"][0]
    como("cocina").post(f"/api/cocina/items/{detalle['id']}/listo")

    r = _quitar(mesero, pedido, detalle, motivo="el cliente se arrepintió")
    assert r.status_code == 403
    assert "ya preparó" in r.json()["detail"]


def test_el_administrador_corrige_sin_codigo(como, db, datos):
    pedido = _enviar(como("mesero"), 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    detalle = pedido["detalles"][0]
    _envejecer(db, detalle["id"], minutos=60)

    assert _quitar(como("admin"), pedido, detalle).status_code == 200


def test_una_mesa_ya_cobrada_no_se_corrige(cliente, como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 2})
    cliente.post(f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"})

    assert _quitar(mesero, pedido, pedido["detalles"][0]).status_code == 409


# ----------------------------------------------- lo que pasa después


def test_un_plato_quitado_desaparece_de_la_cocina(como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"plato_id": datos["picada"].id, "cantidad": 1})
    _quitar(mesero, pedido, pedido["detalles"][0], motivo="mesa equivocada")

    assert como("cocina").get("/api/cocina/pendientes").json() == []


def test_la_caja_cobra_lo_corregido(cliente, como, datos):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 3})
    _quitar(mesero, pedido, pedido["detalles"][0])

    venta = cliente.post(
        f"/api/pedidos/{pedido['id']}/cobrar", json={"metodo_pago": "efectivo"}
    ).json()
    assert venta["total"] == 7000


def test_el_dueno_ve_cada_correccion(como, otro_mesero, datos, codigo_puesto):
    mesero = como("mesero")
    pedido = _enviar(mesero, 4, {"producto_id": datos["cerveza"].id, "cantidad": 3})
    detalle = pedido["detalles"][0]
    _quitar(mesero, pedido, detalle, motivo="se anotó de más")
    _quitar(otro_mesero, pedido, detalle, motivo="cliente reclamó", codigo_autorizacion=CODIGO)

    correcciones = como("admin").get("/api/reportes/novedades").json()["correcciones"]

    assert len(correcciones) == 2
    por_motivo = {c["motivo"]: c for c in correcciones}
    assert por_motivo["se anotó de más"]["quien"] == "mesero"
    assert por_motivo["se anotó de más"]["con_codigo"] is False
    assert por_motivo["cliente reclamó"]["quien"] == "mesero2"
    assert por_motivo["cliente reclamó"]["con_codigo"] is True
    assert por_motivo["cliente reclamó"]["que"] == "Mesa 4 · 1 × Cerveza Aguila 330ml"
    assert por_motivo["cliente reclamó"]["monto"] == 3500
