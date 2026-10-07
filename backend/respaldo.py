"""Hace una copia de seguridad de la base, ahora mismo.

Uso:  .venv\\Scripts\\python.exe respaldo.py

El servidor ya hace una copia al arrancar cada día. Este script sirve para
forzar una copia antes de algo riesgoso: migrar, cargar inventario en masa,
o cerrar el mes.

Ojo: guarda en el mismo computador, lo que protege contra un borrado o un
archivo corrupto — no contra un robo o un incendio. Vale la pena que la
carpeta de respaldos también se sincronice a una nube.
"""

import sys

from app.config import CARPETA_RESPALDOS, DIAS_DE_RESPALDO
from app.respaldos import borrar_viejas, copiar, respaldo_manual


def main() -> int:
    destino = respaldo_manual()
    bytes_copiados = copiar(destino)
    print(f"Copia guardada en {destino} ({bytes_copiados / 1024:.0f} KB)")

    borradas = borrar_viejas()
    if borradas:
        print(f"Se borraron {len(borradas)} copias de más de {DIAS_DE_RESPALDO} días.")

    cuantas = len(list(CARPETA_RESPALDOS.glob("elcampus-*.db")))
    print(f"Hay {cuantas} copias guardadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
