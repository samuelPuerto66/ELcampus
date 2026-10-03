from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth import crear_token
from app.database import Base, get_db
from app.main import app
from app.security import hash_password


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def datos(db):
    usuarios = {
        "admin": models.Usuario(
            nombre="admin",
            rol=models.RolUsuario.administrador,
            password_hash=hash_password("clave-de-prueba"),
        ),
        "vendedor": models.Usuario(
            nombre="vendedor",
            rol=models.RolUsuario.vendedor,
            password_hash=hash_password("clave-de-prueba"),
        ),
        "mesero": models.Usuario(
            nombre="mesero",
            rol=models.RolUsuario.mesero,
            password_hash=hash_password("clave-de-prueba"),
        ),
        "cocina": models.Usuario(
            nombre="cocina",
            rol=models.RolUsuario.cocina,
            password_hash=hash_password("clave-de-prueba"),
        ),
    }
    cerveza = models.Producto(
        codigo_barras="7701234567890",
        nombre="Cerveza Aguila 330ml",
        precio=3500,
        costo=2300,
        stock_actual=100,
    )
    morraja = models.Producto(
        codigo_barras="MORRAJA-KG",
        nombre="Morraja",
        precio=0,
        tipo_venta=models.TipoVenta.peso,
        precio_por_kg=18000,
        costo=11000,
        stock_actual=20,
    )
    # Sin costo a propósito: sirve para probar que la utilidad avisa cuando
    # hay líneas de las que no se sabe cuánto costaron.
    picada = models.Plato(nombre="Picada", precio=45000, tipo=models.TipoPlato.fijo)

    db.add_all([*usuarios.values(), cerveza, morraja, picada])
    db.commit()

    return {
        **usuarios,
        "cerveza": cerveza,
        "morraja": morraja,
        "picada": picada,
    }


@pytest.fixture(autouse=True)
def caja_abierta(request, db, datos):
    """Casi toda prueba vende, y vender exige un turno de caja abierto.

    Las pruebas que manejan el turno ellas mismas se marcan con
    `@pytest.mark.sin_caja` para que esto no se les adelante.
    """
    if "sin_caja" in request.keywords:
        return None

    turno = models.CierreCaja(
        fecha=date.today(), base_inicial=0, usuario_id=datos["vendedor"].id
    )
    db.add(turno)
    db.commit()
    return turno


@pytest.fixture
def cliente(db, datos):
    """Cliente autenticado como vendedor, que es quien cobra."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {crear_token(datos['vendedor'])}"
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def como(db, datos):
    """Fabrica clientes con otro rol: como('mesero'), como('admin')."""
    app.dependency_overrides[get_db] = lambda: db

    def fabricar(rol: str) -> TestClient:
        c = TestClient(app)
        c.headers["Authorization"] = f"Bearer {crear_token(datos[rol])}"
        return c

    yield fabricar
    app.dependency_overrides.clear()
