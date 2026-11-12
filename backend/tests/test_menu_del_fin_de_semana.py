"""El menú del restaurante cambia cada fin de semana.

La picada, la pechuga y la mojarra son fijas: van siempre. Los demás platos
rotan — el administrador marca cuáles salen este fin de semana y los publica.
Lo que no marcó deja de aparecerle al mesero, pero no se borra: sigue en la
carta esperando su turno.
"""

from datetime import date, timedelta

import pytest

from app import models


@pytest.fixture
def carta(db, datos):
    """Tres platos que rotan, ninguno puesto todavía."""
    platos = {
        nombre: models.Plato(nombre=nombre, precio=precio, tipo=models.TipoPlato.especial)
        for nombre, precio in [
            ("Sancocho de gallina", 28000),
            ("Ajiaco", 30000),
            ("Mondongo", 30000),
        ]
    }
    db.add_all(platos.values())
    db.commit()
    return platos


def nombres_del_menu(cliente):
    return {p["nombre"] for p in cliente.get("/api/platos").json()}


def publicar(cliente, ids, desde=None, hasta=None):
    hoy = date.today()
    return cliente.post(
        "/api/platos/menu",
        json={
            "desde": str(desde or hoy),
            "hasta": str(hasta or hoy + timedelta(days=2)),
            "platos": ids,
        },
    )


# ------------------------------------------------------- lo que ve el mesero


def test_un_plato_guardado_no_le_sale_al_mesero(como, carta):
    """Está en la carta, pero el administrador no lo ha sacado todavía."""
    assert "Ajiaco" not in nombres_del_menu(como("mesero"))


def test_los_fijos_salen_siempre(como, carta, datos):
    """La picada no depende de que nadie la publique."""
    assert "Picada" in nombres_del_menu(como("mesero"))


def test_el_admin_saca_los_platos_del_fin_de_semana(como, carta):
    admin = como("admin")
    respuesta = publicar(admin, [carta["Ajiaco"].id, carta["Mondongo"].id])
    assert respuesta.status_code == 200

    menu = nombres_del_menu(como("mesero"))
    assert "Ajiaco" in menu
    assert "Mondongo" in menu
    assert "Sancocho de gallina" not in menu
    assert "Picada" in menu


def test_publicar_de_nuevo_saca_lo_que_ya_no_va(como, carta):
    """El fin de semana siguiente se cambian los platos."""
    admin = como("admin")
    publicar(admin, [carta["Ajiaco"].id])
    assert "Ajiaco" in nombres_del_menu(como("mesero"))

    publicar(admin, [carta["Mondongo"].id])
    menu = nombres_del_menu(como("mesero"))
    assert "Mondongo" in menu
    assert "Ajiaco" not in menu


def test_publicar_sin_nada_deja_solo_los_fijos(como, carta, datos):
    admin = como("admin")
    publicar(admin, [])
    assert nombres_del_menu(como("mesero")) == {"Picada"}


def test_lo_que_se_saca_sigue_en_la_carta(como, carta):
    """No se borra: la semana entrante se puede volver a sacar."""
    admin = como("admin")
    publicar(admin, [carta["Ajiaco"].id])
    publicar(admin, [])

    completa = {p["nombre"] for p in admin.get("/api/platos?solo_vigentes=false").json()}
    assert "Ajiaco" in completa


# ------------------------------------------------------------- las fechas


def test_el_menu_de_la_semana_pasada_se_apaga_solo(como, db, carta):
    """Nadie tiene que acordarse el lunes."""
    plato = carta["Ajiaco"]
    plato.activo_desde = date.today() - timedelta(days=9)
    plato.activo_hasta = date.today() - timedelta(days=7)
    db.commit()

    assert "Ajiaco" not in nombres_del_menu(como("mesero"))


def test_un_menu_programado_para_despues_no_se_adelanta(como, db, carta):
    plato = carta["Ajiaco"]
    plato.activo_desde = date.today() + timedelta(days=3)
    plato.activo_hasta = date.today() + timedelta(days=5)
    db.commit()

    assert "Ajiaco" not in nombres_del_menu(como("mesero"))


def test_las_fechas_al_reves_se_rechazan(como, carta):
    hoy = date.today()
    respuesta = publicar(
        como("admin"), [carta["Ajiaco"].id], desde=hoy, hasta=hoy - timedelta(days=2)
    )
    assert respuesta.status_code == 422
    assert "anterior" in respuesta.json()["detail"]


def test_un_menu_rechazado_no_cambia_nada(como, db, carta):
    """Si la fecha está mal, el menú que ya estaba sigue igual."""
    admin = como("admin")
    publicar(admin, [carta["Ajiaco"].id])

    hoy = date.today()
    publicar(admin, [carta["Mondongo"].id], desde=hoy, hasta=hoy - timedelta(days=1))

    assert "Ajiaco" in nombres_del_menu(como("mesero"))


# ------------------------------------------------------------- quién puede


def test_un_plato_que_no_existe_se_rechaza(como, carta):
    respuesta = publicar(como("admin"), [9999])
    assert respuesta.status_code == 404


def test_un_plato_fijo_no_se_maneja_por_aqui(como, carta, datos):
    """Los fijos van siempre; mandarlos por aquí es un error, no un cambio."""
    respuesta = publicar(como("admin"), [datos["picada"].id])
    assert respuesta.status_code == 404


def test_el_mesero_no_arma_el_menu(como, carta):
    assert publicar(como("mesero"), [carta["Ajiaco"].id]).status_code == 403


def test_el_vendedor_tampoco(cliente, carta):
    assert publicar(cliente, [carta["Ajiaco"].id]).status_code == 403
