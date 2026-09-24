"""Pone la base al día sin borrar lo que ya tiene dentro.

Uso:  .venv\\Scripts\\python.exe migrar.py

Se puede correr las veces que haga falta: cada paso mira primero si ya está
hecho. El proyecto todavía no usa Alembic, y `create_all` crea tablas nuevas
pero no agrega columnas a las que ya existen — de ahí este archivo.
"""

import sys

from sqlalchemy import text

from app.database import engine


def columnas(con, tabla: str) -> set[str]:
    return {fila[1] for fila in con.execute(text(f"PRAGMA table_info({tabla})"))}


def main() -> int:
    hechos = []

    with engine.begin() as con:
        # --- correo de usuario (opcional, único) ---
        if "correo" not in columnas(con, "usuarios"):
            con.execute(text("ALTER TABLE usuarios ADD COLUMN correo VARCHAR(180)"))
            hechos.append("usuarios.correo agregada")

        # El índice único va aparte: SQLite no deja añadir la restricción en
        # el ALTER, pero un índice único hace exactamente lo mismo. Y es
        # parcial para que varios usuarios sin correo no choquen entre sí.
        indices = {fila[1] for fila in con.execute(text("PRAGMA index_list(usuarios)"))}
        if "ix_usuarios_correo" not in indices:
            con.execute(
                text(
                    "CREATE UNIQUE INDEX ix_usuarios_correo ON usuarios(correo) "
                    "WHERE correo IS NOT NULL"
                )
            )
            hechos.append("índice único de correo creado")

        if "ix_usuarios_nombre" not in indices:
            con.execute(
                text("CREATE UNIQUE INDEX ix_usuarios_nombre ON usuarios(nombre)")
            )
            hechos.append("índice único de nombre creado")

    if hechos:
        for h in hechos:
            print(f"  · {h}")
        print("\nBase actualizada.")
    else:
        print("La base ya estaba al día. No se cambió nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
