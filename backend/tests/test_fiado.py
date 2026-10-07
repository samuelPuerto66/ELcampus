"""El cuaderno de fiados: a quién se le fía, cuánto debe y cómo paga.

Lo que más importa aquí es que la plata cuadre: lo fiado no entra al
cajón, lo abonado en efectivo sí, y la deuda de cada cliente siempre es
exactamente lo fiado menos lo abonado.
"""

from datetime import date

import pytest

from app import models


@pytest.fixture
def don_pedro(como):
    """Un cliente con cupo de $20.000, registrado por el administrador."""
    r = como("admin").post(
        "/api/fiado/clientes",
        json={"nombre": "Don Pedro", "telefono": "300 123 4567", "cupo": 20000},
    )
    assert r.status_code == 201
    return r.json()


def _fiar(cliente_http, datos, cliente_fiado_id, cantidad=2, **cobro):
    """Cervezas a $3.500 fiadas en el mostrador."""
    cuerpo = {
        "tipo": "mostrador",
        "metodo_pago": "fiado",
        "cliente_fiado_id": cliente_fiado_id,
        "items": [{"producto_id": datos["cerveza"].id, "cantidad": cantidad}],
        **cobro,
    }
    return cliente_http.post("/api/ventas", json=cuerpo)


def _saldo(c, cliente_id):
    return c.get(f"/api/fiado/clientes/{cliente_id}").json()["saldo"]


def _abonar(c, cliente_id, monto, metodo="efectivo"):
    return c.post(
        f"/api/fiado/clientes/{cliente_id}/abonos", json={"monto": monto, "metodo": metodo}
    )


def _efectivo_esperado(c) -> float:
    return c.post("/api/caja/cerrar", json={"efectivo_contado": 0}).json()["efectivo_esperado"]


# ----------------------------------------------------------- quién decide


def test_solo_el_administrador_registra_a_quien_se_le_fia(cliente, como):
    r = cliente.post("/api/fiado/clientes", json={"nombre": "Doña Marta"})
    assert r.status_code == 403
    assert como("mesero").get("/api/fiado/clientes").status_code == 403


def test_no_se_repite_un_cliente_aunque_cambien_las_mayusculas(como, don_pedro):
    r = como("admin").post("/api/fiado/clientes", json={"nombre": "don pedro"})
    assert r.status_code == 409
    assert "apellido" in r.json()["detail"]


# ------------------------------------------------------------ fiar


def test_vender_fiado_deja_la_deuda_anotada(cliente, datos, don_pedro):
    r = _fiar(cliente, datos, don_pedro["id"])
    assert r.status_code == 201
    venta = r.json()
    assert venta["metodo_pago"] == "fiado"
    assert venta["cliente_fiado_id"] == don_pedro["id"]

    assert _saldo(cliente, don_pedro["id"]) == 7000


def test_lo_fiado_no_entra_al_cajon(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"])
    assert _efectivo_esperado(cliente) == 0


def test_fiar_sin_decir_a_quien_no_se_puede(cliente, datos):
    r = _fiar(cliente, datos, None)
    assert r.status_code == 400
    assert "a quién" in r.json()["detail"]


def test_no_se_fia_por_encima_del_cupo(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"], cantidad=4)  # debe $14.000 de $20.000
    r = _fiar(cliente, datos, don_pedro["id"], cantidad=2)  # $7.000 más: se pasa
    assert r.status_code == 409
    assert "debe $14.000" in r.json()["detail"]
    assert "cupo es $20.000" in r.json()["detail"]
    # Y nada quedó a medias: ni venta ni inventario.
    assert _saldo(cliente, don_pedro["id"]) == 14000


def test_sin_cupo_no_hay_limite(cliente, como, datos):
    sin_cupo = como("admin").post("/api/fiado/clientes", json={"nombre": "La tía"}).json()
    assert _fiar(cliente, datos, sin_cupo["id"], cantidad=20).status_code == 201


def test_a_un_cliente_apagado_no_se_le_fia(cliente, como, datos, don_pedro):
    como("admin").patch(f"/api/fiado/clientes/{don_pedro['id']}", json={"activo": False})
    r = _fiar(cliente, datos, don_pedro["id"])
    assert r.status_code == 409
    assert "ya no se le fía" in r.json()["detail"]


def test_pagar_una_parte_y_fiar_el_resto(cliente, datos, don_pedro):
    r = _fiar(
        cliente,
        datos,
        don_pedro["id"],
        cantidad=4,  # $14.000
        metodo_pago=None,
        pagos=[{"metodo": "efectivo", "monto": 10000}, {"metodo": "fiado", "monto": 4000}],
    )
    assert r.status_code == 201
    assert _saldo(cliente, don_pedro["id"]) == 4000
    assert _efectivo_esperado(cliente) == 10000


def test_anular_una_venta_fiada_borra_la_deuda(cliente, datos, don_pedro):
    venta = _fiar(cliente, datos, don_pedro["id"]).json()
    cliente.post(f"/api/ventas/{venta['id']}/anular", json={"motivo": "error"})
    assert _saldo(cliente, don_pedro["id"]) == 0


# ------------------------------------------------------------ abonos


def test_un_abono_baja_la_deuda_y_entra_al_cajon(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"], cantidad=4)  # $14.000
    r = _abonar(cliente, don_pedro["id"], 10000)
    assert r.status_code == 201

    assert _saldo(cliente, don_pedro["id"]) == 4000
    assert _efectivo_esperado(cliente) == 10000


def test_un_abono_por_nequi_no_va_al_cajon(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"], cantidad=4)
    _abonar(cliente, don_pedro["id"], 10000, metodo="nequi")
    assert _efectivo_esperado(cliente) == 0


def test_no_se_recibe_mas_de_lo_que_debe(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"])  # $7.000
    r = _abonar(cliente, don_pedro["id"], 70000)
    assert r.status_code == 400
    assert "solo debe $7.000" in r.json()["detail"]


@pytest.mark.sin_caja
def test_sin_caja_abierta_no_se_reciben_abonos(cliente, db, datos, don_pedro):
    # Se fía con un turno, se cierra, y se intenta abonar con la caja cerrada.
    db.add(
        models.CierreCaja(fecha=date.today(), base_inicial=0, usuario_id=datos["vendedor"].id)
    )
    db.commit()
    _fiar(cliente, datos, don_pedro["id"])
    cliente.post("/api/caja/cerrar", json={"efectivo_contado": 0})

    r = _abonar(cliente, don_pedro["id"], 1000)
    assert r.status_code == 409


def test_un_abono_por_fiado_no_tiene_sentido(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"])
    assert _abonar(cliente, don_pedro["id"], 1000, metodo="fiado").status_code == 422


def test_anular_un_abono_vuelve_a_subir_la_deuda_y_saca_la_plata(
    cliente, como, datos, don_pedro
):
    _fiar(cliente, datos, don_pedro["id"], cantidad=4)
    abono = _abonar(cliente, don_pedro["id"], 10000).json()

    # El vendedor no puede anularlo.
    r = cliente.post(f"/api/fiado/abonos/{abono['id']}/anular", json={"motivo": "x"})
    assert r.status_code == 403

    r = como("admin").post(
        f"/api/fiado/abonos/{abono['id']}/anular", json={"motivo": "se registró dos veces"}
    )
    assert r.status_code == 200

    assert _saldo(cliente, don_pedro["id"]) == 14000
    assert _efectivo_esperado(cliente) == 0


# ------------------------------------------------------------ la cuenta


def test_la_cuenta_muestra_lo_que_se_llevo_y_lo_que_abono(cliente, datos, don_pedro):
    _fiar(cliente, datos, don_pedro["id"], cantidad=2)
    _abonar(cliente, don_pedro["id"], 5000)

    cuenta = cliente.get(f"/api/fiado/clientes/{don_pedro['id']}").json()

    assert cuenta["saldo"] == 2000
    tipos = [(m["tipo"], m["monto"]) for m in cuenta["movimientos"]]
    assert ("fiado", 7000) in tipos
    assert ("abono", 5000) in tipos
    fiado = next(m for m in cuenta["movimientos"] if m["tipo"] == "fiado")
    assert fiado["detalle"] == "2 × Cerveza Aguila 330ml"


def test_la_lista_pone_primero_a_los_que_mas_deben(cliente, como, datos, don_pedro):
    la_tia = como("admin").post("/api/fiado/clientes", json={"nombre": "La tía"}).json()
    _fiar(cliente, datos, don_pedro["id"], cantidad=1)
    _fiar(cliente, datos, la_tia["id"], cantidad=3)

    lista = cliente.get("/api/fiado/clientes").json()
    assert [c["nombre"] for c in lista] == ["La tía", "Don Pedro"]
    assert [c["saldo"] for c in lista] == [10500, 3500]


def test_el_resumen_del_dia_separa_lo_fiado_de_la_plata(
    cliente, datos, don_pedro, ver_resumen
):
    _fiar(cliente, datos, don_pedro["id"], cantidad=4)  # $14.000 fiados
    _abonar(cliente, don_pedro["id"], 4000)

    resumen = ver_resumen()
    # Se vendió, aunque no haya entrado la plata todavía.
    assert resumen["total"] == 14000
    assert resumen["fiado_del_dia"] == 14000
    assert resumen["abonos_del_dia"] == 4000
    assert resumen["te_deben"] == 10000
    # "Cómo entró la plata" no cuenta lo fiado.
    assert all(m["metodo_pago"] != "fiado" for m in resumen["por_metodo"])
