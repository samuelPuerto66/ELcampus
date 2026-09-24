"""Fija el código que los administradores escriben además de su clave.

Uso:  .venv\\Scripts\\python.exe codigo_admin.py

Lo pide por teclado sin mostrarlo y guarda solo el hash en backend/.codigo-admin,
que está fuera del repositorio. Nadie —ni quien lea el código, ni quien abra la
base de datos— puede recuperar el código a partir de lo guardado: si se olvida,
se vuelve a correr este script y se pone uno nuevo.
"""

import getpass
import sys

from app.config import ARCHIVO_CODIGO_ADMIN, guardar_codigo_admin, hash_del_codigo_admin
from app.security import hash_password

MINIMO = 6


def main() -> int:
    if hash_del_codigo_admin():
        print("Ya hay un código configurado. Si sigues, lo reemplazas.")
        if input("¿Continuar? (s/n): ").strip().lower() not in ("s", "si", "sí"):
            print("Sin cambios.")
            return 0

    codigo = getpass.getpass("Código de administrador (no se ve al escribir): ")
    if len(codigo) < MINIMO:
        print(f"Muy corto: necesita al menos {MINIMO} caracteres.")
        return 1

    if codigo != getpass.getpass("Escríbelo otra vez para confirmar: "):
        print("Los dos códigos no coinciden. No se guardó nada.")
        return 1

    guardar_codigo_admin(hash_password(codigo))
    print(f"\nListo. Guardado en {ARCHIVO_CODIGO_ADMIN}")
    print("Los administradores ya pueden entrar con su clave y este código.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
