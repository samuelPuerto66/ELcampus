"""Entrada por correo, código de administrador y registro de usuarios."""

import pytest
from fastapi.testclient import TestClient

from app import config, models
from app.database import get_db
from app.main import app
from app.security import hash_password

CODIGO = "brasa-2026"


@pytest.fixture
def codigo_puesto(tmp_path, monkeypatch):
    """Deja un código de administrador configurado, fuera del archivo real."""
    archivo = tmp_path / ".codigo-admin"
    archivo.write_text(hash_password(CODIGO), encoding="utf-8")
    monkeypatch.setattr(config, "ARCHIVO_CODIGO_ADMIN", archivo)
    return archivo


@pytest.fixture
def sin_codigo(tmp_path, monkeypatch):
    """Simula un servidor donde nadie configuró todavía el código."""
    monkeypatch.setattr(config, "ARCHIVO_CODIGO_ADMIN", tmp_path / "no-existe")


@pytest.fixture
def anonimo(db, datos):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def entrar(c, nombre, clave="clave-de-prueba", codigo=None):
    cuerpo = {"nombre": nombre, "clave": clave}
    if codigo is not None:
        cuerpo["codigo"] = codigo
    return c.post("/api/auth/entrar", json=cuerpo)


# ------------------------------------------------------- entrar por correo


def test_el_empleado_entra_con_su_nombre(anonimo):
    respuesta = entrar(anonimo, "vendedor")
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "vendedor"


def test_el_empleado_entra_con_su_correo(anonimo, db, datos):
    datos["mesero"].correo = "carlos@elcampus.co"
    db.commit()

    respuesta = entrar(anonimo, "carlos@elcampus.co")
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "mesero"


def test_el_correo_no_distingue_mayusculas(anonimo, db, datos):
    datos["mesero"].correo = "carlos@elcampus.co"
    db.commit()

    assert entrar(anonimo, "Carlos@ElCampus.CO").status_code == 200


def test_un_correo_que_no_existe_se_rechaza(anonimo):
    assert entrar(anonimo, "nadie@elcampus.co").status_code == 401


# --------------------------------------------- código de administrador


def test_el_admin_sin_codigo_no_entra(anonimo, codigo_puesto):
    respuesta = entrar(anonimo, "admin")
    assert respuesta.status_code == 401
    assert "código" in respuesta.json()["detail"].lower()


def test_el_admin_con_codigo_equivocado_no_entra(anonimo, codigo_puesto):
    assert entrar(anonimo, "admin", codigo="el-que-no-es").status_code == 401


def test_el_admin_con_codigo_correcto_entra(anonimo, codigo_puesto):
    respuesta = entrar(anonimo, "admin", codigo=CODIGO)
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "administrador"


def test_la_clave_correcta_con_codigo_correcto_no_basta_si_la_clave_falla(
    anonimo, codigo_puesto
):
    respuesta = entrar(anonimo, "admin", clave="la-que-no-es", codigo=CODIGO)
    assert respuesta.status_code == 401


def test_al_empleado_no_le_piden_codigo(anonimo, codigo_puesto):
    assert entrar(anonimo, "vendedor").status_code == 200


def test_el_codigo_de_un_empleado_se_ignora(anonimo, codigo_puesto):
    """Mandar código de más no rompe nada para quien no lo necesita."""
    assert entrar(anonimo, "mesero", codigo="cualquier-cosa").status_code == 200


def test_sin_codigo_configurado_el_admin_no_puede_entrar(anonimo, sin_codigo):
    """Falla cerrado: sin código configurado, nadie entra como administrador."""
    respuesta = entrar(anonimo, "admin", codigo="lo-que-sea")
    assert respuesta.status_code == 503
    assert "no está configurado" in respuesta.json()["detail"]


def test_sin_codigo_configurado_los_empleados_siguen_entrando(anonimo, sin_codigo):
    assert entrar(anonimo, "vendedor").status_code == 200


def test_el_formulario_de_docs_no_deja_entrar_al_admin(anonimo, codigo_puesto):
    """El formulario OAuth2 no tiene dónde poner el código."""
    respuesta = anonimo.post(
        "/api/auth/login", data={"username": "admin", "password": "clave-de-prueba"}
    )
    assert respuesta.status_code == 401


# --------------------------------------------------- registro de usuarios


def nuevo(c, **campos):
    cuerpo = {
        "nombre": "carlos",
        "clave": "clave-nueva",
        "rol": "mesero",
        **campos,
    }
    return c.post("/api/auth/usuarios", json=cuerpo)


def test_el_admin_registra_un_mesero(como, datos):
    respuesta = nuevo(como("admin"), rol="mesero", correo="carlos@elcampus.co")
    assert respuesta.status_code == 201
    creado = respuesta.json()
    assert creado["rol"] == "mesero"
    assert creado["correo"] == "carlos@elcampus.co"
    assert creado["activo"] is True


def test_el_admin_registra_un_vendedor(como, datos):
    respuesta = nuevo(como("admin"), rol="vendedor")
    assert respuesta.status_code == 201
    assert respuesta.json()["rol"] == "vendedor"
    assert respuesta.json()["correo"] is None


def test_el_correo_se_guarda_en_minusculas(como, datos):
    respuesta = nuevo(como("admin"), correo="Carlos@ElCampus.CO")
    assert respuesta.json()["correo"] == "carlos@elcampus.co"


def test_un_registrado_puede_entrar(como, anonimo, datos):
    nuevo(como("admin"), correo="carlos@elcampus.co")
    assert entrar(anonimo, "carlos", clave="clave-nueva").status_code == 200
    assert entrar(anonimo, "carlos@elcampus.co", clave="clave-nueva").status_code == 200


def test_no_se_repite_el_nombre(como, datos):
    assert nuevo(como("admin"), nombre="vendedor").status_code == 409


def test_no_se_repite_el_correo(como, datos):
    c = como("admin")
    nuevo(c, nombre="carlos", correo="repetido@elcampus.co")
    respuesta = nuevo(c, nombre="ana", correo="repetido@elcampus.co")
    assert respuesta.status_code == 409


def test_el_correo_mal_escrito_se_rechaza(como, datos):
    assert nuevo(como("admin"), correo="esto-no-es-un-correo").status_code == 422


def test_la_clave_muy_corta_se_rechaza(como, datos):
    assert nuevo(como("admin"), clave="123").status_code == 422


def test_el_vendedor_no_puede_registrar_usuarios(cliente, datos):
    assert nuevo(cliente).status_code == 403


# ----------------------------------------------------- editar usuarios


def test_el_admin_le_cambia_la_clave_a_un_empleado(como, anonimo, datos):
    admin = como("admin")
    respuesta = admin.patch(
        f"/api/auth/usuarios/{datos['mesero'].id}", json={"clave": "clave-cambiada"}
    )
    assert respuesta.status_code == 200
    assert entrar(anonimo, "mesero", clave="clave-cambiada").status_code == 200
    assert entrar(anonimo, "mesero", clave="clave-de-prueba").status_code == 401


def test_el_admin_cambia_de_mesero_a_vendedor(como, datos):
    respuesta = como("admin").patch(
        f"/api/auth/usuarios/{datos['mesero'].id}", json={"rol": "vendedor"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["rol"] == "vendedor"


def test_el_admin_le_pone_correo_a_quien_no_tenia(como, datos):
    respuesta = como("admin").patch(
        f"/api/auth/usuarios/{datos['vendedor'].id}",
        json={"correo": "vendedor@elcampus.co"},
    )
    assert respuesta.json()["correo"] == "vendedor@elcampus.co"


def test_el_admin_no_puede_desactivarse_a_si_mismo(como, datos):
    respuesta = como("admin").patch(
        f"/api/auth/usuarios/{datos['admin'].id}", json={"activo": False}
    )
    assert respuesta.status_code == 400


def test_el_admin_no_puede_quitarse_el_cargo(como, datos):
    """Si no, el negocio se queda sin nadie que administre."""
    respuesta = como("admin").patch(
        f"/api/auth/usuarios/{datos['admin'].id}", json={"rol": "mesero"}
    )
    assert respuesta.status_code == 400


def test_un_desactivado_no_entra(como, anonimo, datos):
    como("admin").patch(
        f"/api/auth/usuarios/{datos['mesero'].id}", json={"activo": False}
    )
    assert entrar(anonimo, "mesero").status_code == 403


def test_el_vendedor_no_puede_editar_usuarios(cliente, datos):
    respuesta = cliente.patch(
        f"/api/auth/usuarios/{datos['mesero'].id}", json={"rol": "administrador"}
    )
    assert respuesta.status_code == 403
