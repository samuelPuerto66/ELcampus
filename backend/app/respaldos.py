"""Copias de seguridad de la base.

Toda la plata del negocio vive en un archivo. Si ese disco falla un sábado
sin copia, se pierden las ventas, el inventario y el historial completo.

La copia se hace con el mecanismo propio de SQLite, no copiando el archivo:
así queda consistente aunque alguien esté cobrando en ese mismo momento.
"""

import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import CARPETA_RESPALDOS, DATABASE_URL, DIAS_DE_RESPALDO


def ruta_de_la_base() -> Path:
    if not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError(f"Esto solo sirve para SQLite, no para {DATABASE_URL}")
    return Path(DATABASE_URL.removeprefix("sqlite:///"))


def respaldo_del_dia() -> Path:
    return CARPETA_RESPALDOS / f"elcampus-{date.today():%Y-%m-%d}.db"


def copiar(destino: Path) -> int:
    """Copia consistente aunque la caja esté cobrando. Devuelve los bytes."""
    origen = ruta_de_la_base()
    if not origen.exists():
        raise FileNotFoundError(f"No existe la base en {origen}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    con_origen = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    try:
        con_destino = sqlite3.connect(destino)
        try:
            con_origen.backup(con_destino)
        finally:
            con_destino.close()
    finally:
        con_origen.close()

    return destino.stat().st_size


def borrar_viejas() -> list[str]:
    limite = date.today() - timedelta(days=DIAS_DE_RESPALDO)
    borradas = []
    for archivo in CARPETA_RESPALDOS.glob("elcampus-*.db"):
        try:
            cuando = datetime.strptime(
                archivo.stem.removeprefix("elcampus-"), "%Y-%m-%d"
            ).date()
        except ValueError:
            continue
        if cuando < limite:
            archivo.unlink()
            borradas.append(archivo.name)
    return borradas


def hacer_respaldo_si_falta() -> Path | None:
    """Copia de hoy si todavía no existe. La llama el servidor al arrancar.

    El PC de la caja se prende casi todos los días, así que esto solo ya da
    una copia diaria sin que nadie se acuerde de hacerla.
    """
    # Las pruebas levantan la app muchas veces y no deben tocar la base real.
    if "pytest" in sys.modules:
        return None

    destino = respaldo_del_dia()
    if destino.exists():
        return None
    try:
        copiar(destino)
        borrar_viejas()
        return destino
    except Exception:
        # Un respaldo que falla nunca debe impedir que la caja abra.
        return None
