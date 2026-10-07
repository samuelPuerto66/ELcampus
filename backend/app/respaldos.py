"""Copias de seguridad de la base.

Toda la plata del negocio vive en un archivo. Si ese disco falla un sábado
sin copia, se pierden las ventas, el inventario y el historial completo.

La copia se hace con el mecanismo propio de SQLite, no copiando el archivo:
así queda consistente aunque alguien esté cobrando en ese mismo momento.
"""

import asyncio
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import (
    CARPETA_RESPALDOS,
    DATABASE_URL,
    DIAS_DE_RESPALDO,
    MINUTOS_ENTRE_REVISIONES_DE_RESPALDO,
)


def ruta_de_la_base() -> Path:
    if not DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError(f"Esto solo sirve para SQLite, no para {DATABASE_URL}")
    return Path(DATABASE_URL.removeprefix("sqlite:///"))


def respaldo_del_dia() -> Path:
    """La copia automática: una por día."""
    return CARPETA_RESPALDOS / f"elcampus-{date.today():%Y-%m-%d}.db"


def respaldo_manual() -> Path:
    """Una copia a mano, con la hora en el nombre.

    Lleva la hora para no pisar la copia automática del día: si alguien
    hace una copia "antes de algo riesgoso" cuando el daño ya está hecho,
    la copia buena de la mañana tiene que seguir ahí.
    """
    return CARPETA_RESPALDOS / f"elcampus-{datetime.now():%Y-%m-%d-%H%M%S}.db"


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
            # Los primeros 10 caracteres son la fecha, tenga o no la hora.
            cuando = datetime.strptime(
                archivo.stem.removeprefix("elcampus-")[:10], "%Y-%m-%d"
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


async def respaldar_cada_dia() -> None:
    """Revisa de vez en cuando si ya está la copia de hoy, y si no, la hace.

    Respaldar solo al arrancar no basta: en temporada alta el PC de la caja
    puede quedarse prendido semanas, y la única copia sería la del día en
    que se encendió.
    """
    while True:
        await asyncio.sleep(MINUTOS_ENTRE_REVISIONES_DE_RESPALDO * 60)
        # En otro hilo: copiar la base no debe frenar los cobros.
        copia = await asyncio.to_thread(hacer_respaldo_si_falta)
        if copia is not None:
            print(f"Copia de seguridad del día: {copia}")
