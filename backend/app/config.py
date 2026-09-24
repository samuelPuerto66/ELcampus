import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIST = BASE_DIR.parent / "apps" / "web" / "dist"

DATABASE_URL = os.getenv(
    "ELCAMPUS_DB", f"sqlite:///{(BASE_DIR / 'elcampus.db').as_posix()}"
)


def _cargar_secreto() -> str:
    """Clave para firmar las sesiones.

    Se guarda en un archivo local en vez de quemarla en el código: así las
    sesiones abiertas sobreviven a un reinicio del servidor y la clave nunca
    llega al repositorio.
    """
    del_entorno = os.getenv("ELCAMPUS_SECRET")
    if del_entorno:
        return del_entorno

    archivo = BASE_DIR / ".secreto"
    if not archivo.exists():
        archivo.write_text(secrets.token_hex(32), encoding="utf-8")
    return archivo.read_text(encoding="utf-8").strip()


SECRET_KEY = _cargar_secreto()
ALGORITMO = "HS256"

# Código que además de la clave tiene que escribir quien entra como
# administrador. Es uno solo, compartido entre los administradores: una
# puerta extra, no una identidad. Se guarda hasheado, nunca en texto plano.
ARCHIVO_CODIGO_ADMIN = BASE_DIR / ".codigo-admin"


def hash_del_codigo_admin() -> str | None:
    """El hash guardado, o None si todavía nadie configuró el código."""
    if not ARCHIVO_CODIGO_ADMIN.exists():
        return None
    guardado = ARCHIVO_CODIGO_ADMIN.read_text(encoding="utf-8").strip()
    return guardado or None


def guardar_codigo_admin(hash_nuevo: str) -> None:
    ARCHIVO_CODIGO_ADMIN.write_text(hash_nuevo, encoding="utf-8")

# Un turno completo: el vendedor entra al abrir y no tiene que volver a
# escribir la clave a mitad de un sábado.
HORAS_DE_SESION = 14

ALERTA_STOCK_POR_DEFECTO = 5
