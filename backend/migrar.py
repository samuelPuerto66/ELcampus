"""Pone la base al día sin borrar lo que ya tiene dentro.

Uso:  .venv\\Scripts\\python.exe migrar.py

Se puede correr las veces que haga falta: cada paso mira primero si ya está
hecho. El proyecto todavía no usa Alembic, y `create_all` crea tablas nuevas
pero no agrega columnas a las que ya existen — de ahí este archivo.
"""

import sys

from sqlalchemy import text

from app import models
from app.database import engine


def columnas(con, tabla: str) -> set[str]:
    return {fila[1] for fila in con.execute(text(f"PRAGMA table_info({tabla})"))}


def agregar_columna(con, hechos: list[str], tabla: str, columna: str, tipo: str) -> None:
    """Agrega la columna si todavía no está. Si ya está, no toca nada."""
    if columna not in columnas(con, tabla):
        con.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}"))
        hechos.append(f"{tabla}.{columna} agregada")


def crear_tabla(con, hechos: list[str], modelo) -> None:
    """Crea la tabla de un modelo si todavía no existe.

    Sale tal cual de app/models.py, así que nunca queda distinta de lo que
    el código espera. Puede que ya exista: el servidor crea las tablas
    nuevas solo al arrancar, aunque no sepa agregar columnas.
    """
    tabla = modelo.__table__
    existe = con.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:nombre"),
        {"nombre": tabla.name},
    ).first()
    if existe is None:
        tabla.create(con)
        hechos.append(f"tabla {tabla.name} creada")


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

        # --- costo de productos y platos ---
        if "costo" not in columnas(con, "productos"):
            con.execute(text("ALTER TABLE productos ADD COLUMN costo REAL"))
            hechos.append("productos.costo agregada")

        if "costo" not in columnas(con, "platos"):
            con.execute(text("ALTER TABLE platos ADD COLUMN costo REAL"))
            hechos.append("platos.costo agregada")

        # --- costo congelado en cada línea vendida ---
        if "costo_unitario" not in columnas(con, "detalle_venta"):
            con.execute(text("ALTER TABLE detalle_venta ADD COLUMN costo_unitario REAL"))
            hechos.append("detalle_venta.costo_unitario agregada")

        # --- precio congelado en los pedidos de mesa ---
        # Antes el precio se leía del producto al momento de cobrar, así que
        # subir un precio con mesas abiertas cambiaba cuentas ya pedidas.
        if "precio_unitario" not in columnas(con, "detalle_pedido_mesa"):
            con.execute(
                text(
                    "ALTER TABLE detalle_pedido_mesa "
                    "ADD COLUMN precio_unitario REAL NOT NULL DEFAULT 0"
                )
            )
            con.execute(
                text(
                    """
                    UPDATE detalle_pedido_mesa SET precio_unitario = COALESCE(
                        (SELECT CASE WHEN p.tipo_venta = 'peso'
                                     THEN p.precio_por_kg ELSE p.precio END
                           FROM productos p WHERE p.id = detalle_pedido_mesa.producto_id),
                        (SELECT pl.precio
                           FROM platos pl WHERE pl.id = detalle_pedido_mesa.plato_id),
                        0
                    )
                    """
                )
            )
            hechos.append("detalle_pedido_mesa.precio_unitario agregada y rellenada")

        # --- pantalla de cocina ---
        columnas_detalle = columnas(con, "detalle_pedido_mesa")
        if "estado_cocina" not in columnas_detalle:
            con.execute(
                text(
                    "ALTER TABLE detalle_pedido_mesa ADD COLUMN estado_cocina "
                    "VARCHAR(9) NOT NULL DEFAULT 'pendiente'"
                )
            )
            hechos.append("detalle_pedido_mesa.estado_cocina agregada")

        if "creado_en" not in columnas_detalle:
            # Lo ya pedido queda con la hora en que se abrió su mesa, que es
            # lo más cercano a la verdad que se puede reconstruir.
            con.execute(
                text("ALTER TABLE detalle_pedido_mesa ADD COLUMN creado_en DATETIME")
            )
            con.execute(
                text(
                    """
                    UPDATE detalle_pedido_mesa SET creado_en = COALESCE(
                        (SELECT p.hora_apertura FROM pedidos_mesa p
                          WHERE p.id = detalle_pedido_mesa.pedido_id),
                        CURRENT_TIMESTAMP
                    )
                    WHERE creado_en IS NULL
                    """
                )
            )
            hechos.append("detalle_pedido_mesa.creado_en agregada y rellenada")

        # --- recetas: insumos de cocina ---
        if "es_insumo" not in columnas(con, "productos"):
            con.execute(
                text(
                    "ALTER TABLE productos ADD COLUMN es_insumo "
                    "BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            hechos.append("productos.es_insumo agregada")

        if "venta_id" not in columnas(con, "movimientos_inventario"):
            con.execute(
                text("ALTER TABLE movimientos_inventario ADD COLUMN venta_id INTEGER")
            )
            hechos.append("movimientos_inventario.venta_id agregada")

        existe_insumos = con.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='insumos_plato'")
        ).first()
        if existe_insumos is None:
            con.execute(
                text(
                    """
                    CREATE TABLE insumos_plato (
                        id INTEGER NOT NULL PRIMARY KEY,
                        plato_id INTEGER NOT NULL REFERENCES platos(id),
                        producto_id INTEGER NOT NULL REFERENCES productos(id),
                        cantidad FLOAT NOT NULL
                    )
                    """
                )
            )
            hechos.append("tabla insumos_plato creada")

        # --- descuentos, propinas y pagos divididos ---
        agregar_columna(con, hechos, "ventas", "descuento", "FLOAT NOT NULL DEFAULT 0")
        agregar_columna(con, hechos, "ventas", "motivo_descuento", "VARCHAR")
        agregar_columna(
            con, hechos, "ventas", "descuento_con_codigo", "BOOLEAN NOT NULL DEFAULT 0"
        )
        agregar_columna(con, hechos, "ventas", "propina", "FLOAT NOT NULL DEFAULT 0")
        crear_tabla(con, hechos, models.PagoVenta)
        crear_tabla(con, hechos, models.EnvioMesa)

        # Cada venta vieja tenía un solo método de pago. Se le crea su pago
        # para que el cuadre de caja, que ahora cuenta por pagos, la vea.
        # Va aparte de crear la tabla: el servidor pudo crearla vacía.
        rellenadas = con.execute(
            text(
                """
                INSERT INTO pagos_venta (venta_id, metodo, monto)
                SELECT v.id, v.metodo_pago, v.total + v.propina
                  FROM ventas v
                 WHERE v.total + v.propina > 0
                   AND NOT EXISTS (SELECT 1 FROM pagos_venta p WHERE p.venta_id = v.id)
                """
            )
        ).rowcount
        if rellenadas:
            hechos.append(f"{rellenadas} ventas anteriores pasadas a pagos_venta")

        # --- notas y correcciones de pedidos ---
        agregar_columna(con, hechos, "detalle_pedido_mesa", "agregado_por_id", "INTEGER")
        agregar_columna(con, hechos, "detalle_pedido_mesa", "actualizado_en", "DATETIME")
        crear_tabla(con, hechos, models.CorreccionPedido)

        # --- fiado ---
        # Primero los clientes: los abonos y las ventas apuntan a ellos.
        crear_tabla(con, hechos, models.ClienteFiado)
        crear_tabla(con, hechos, models.AbonoFiado)
        agregar_columna(con, hechos, "ventas", "cliente_fiado_id", "INTEGER")

        # --- platos para llevar ---
        agregar_columna(
            con, hechos, "pedidos_mesa", "para_llevar", "BOOLEAN NOT NULL DEFAULT 0"
        )
        agregar_columna(con, hechos, "pedidos_mesa", "nombre_cliente", "VARCHAR(60)")

    if hechos:
        for h in hechos:
            print(f"  · {h}")
        print("\nBase actualizada.")
    else:
        print("La base ya estaba al día. No se cambió nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
