"""Consulta de un código antes de registrarlo.

El servicio externo se simula: una prueba que depende de internet falla
cuando no debe y pasa a ser ruido en vez de señal.
"""

import pytest

from app.routers import productos as router_productos


@pytest.fixture
def sin_internet(monkeypatch):
    async def nada(_codigo):
        return None

    monkeypatch.setattr(router_productos, "buscar_nombre", nada)


@pytest.fixture
def con_sugerencia(monkeypatch):
    async def sugiere(_codigo):
        return "Coca-Cola 330 ml"

    monkeypatch.setattr(router_productos, "buscar_nombre", sugiere)


def test_un_codigo_ya_registrado_devuelve_el_producto(cliente, datos, sin_internet):
    respuesta = cliente.get("/api/productos/consultar/7701234567890")

    cuerpo = respuesta.json()
    assert cuerpo["registrado"]["nombre"] == "Cerveza Aguila 330ml"
    assert cuerpo["nombre_sugerido"] is None


def test_un_codigo_nuevo_trae_el_nombre_sugerido(cliente, con_sugerencia):
    cuerpo = cliente.get("/api/productos/consultar/5449000000996").json()

    assert cuerpo["registrado"] is None
    assert cuerpo["nombre_sugerido"] == "Coca-Cola 330 ml"


def test_si_el_servicio_externo_no_responde_se_sigue_trabajando(cliente, sin_internet):
    """Sin internet no se bloquea la carga: el nombre se escribe a mano."""
    respuesta = cliente.get("/api/productos/consultar/9999999999999")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["registrado"] is None
    assert cuerpo["nombre_sugerido"] is None


def test_cargar_un_producto_nuevo_queda_listo_para_vender(cliente, con_sugerencia):
    consulta = cliente.get("/api/productos/consultar/5449000000996").json()

    creado = cliente.post(
        "/api/productos",
        json={
            "codigo_barras": consulta["codigo_barras"],
            "nombre": consulta["nombre_sugerido"],
            "precio": 3000,
            "costo": 1900,
            "stock_actual": 24,
            "categoria": "bebidas",
        },
    ).json()

    assert creado["nombre"] == "Coca-Cola 330 ml"
    assert creado["costo"] == 1900

    # Y de una se puede escanear en la caja.
    venta = cliente.post(
        "/api/ventas",
        json={
            "tipo": "mostrador",
            "metodo_pago": "efectivo",
            "items": [{"producto_id": creado["id"], "cantidad": 2}],
        },
    ).json()
    assert venta["total"] == 6000

    resumen = cliente.get("/api/reportes/dia").json()
    assert resumen["utilidad"] == 2200
    assert resumen["lineas_sin_costo"] == 0


def test_no_se_puede_registrar_dos_veces_el_mismo_codigo(cliente, datos, sin_internet):
    respuesta = cliente.post(
        "/api/productos",
        json={
            "codigo_barras": "7701234567890",
            "nombre": "Otra cerveza",
            "precio": 4000,
        },
    )

    assert respuesta.status_code == 409


def test_la_cocina_no_puede_cargar_productos(como, sin_internet):
    respuesta = como("cocina").get("/api/productos/consultar/5449000000996")

    assert respuesta.status_code == 403
