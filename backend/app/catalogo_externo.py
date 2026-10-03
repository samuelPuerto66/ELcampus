"""Autocompletado del nombre de un producto a partir del código de barras.

Es una comodidad para ahorrar tecleo al cargar el inventario, nunca la
fuente de verdad: el arroz de la tienda de la esquina y los platos del fin
de semana no están en ningún catálogo mundial, y eso es normal.

Si el servicio no responde o no conoce el código, se devuelve None y el
usuario escribe el nombre a mano. Nunca se deja esperando a quien está
cargando productos.
"""

import httpx

URL = "https://world.openfoodfacts.org/api/v2/product/{codigo}.json"
CAMPOS = "product_name,product_name_es,brands,quantity"
SEGUNDOS_DE_ESPERA = 4.0


def _armar_nombre(producto: dict) -> str | None:
    nombre = (producto.get("product_name_es") or producto.get("product_name") or "").strip()
    if not nombre:
        return None

    marca = (producto.get("brands") or "").split(",")[0].strip()
    tamano = (producto.get("quantity") or "").strip()

    partes = [nombre]
    # "Aguila" + "Cerveza" → "Cerveza Aguila", no "Cerveza Cerveza Aguila".
    if marca and marca.lower() not in nombre.lower():
        partes.append(marca)
    if tamano and tamano.lower() not in nombre.lower():
        partes.append(tamano)
    return " ".join(partes)[:200]


async def buscar_nombre(codigo_barras: str) -> str | None:
    """El nombre que Open Food Facts conoce para ese código, si lo conoce."""
    try:
        async with httpx.AsyncClient(timeout=SEGUNDOS_DE_ESPERA) as cliente:
            respuesta = await cliente.get(
                URL.format(codigo=codigo_barras),
                params={"fields": CAMPOS},
                headers={"User-Agent": "ElCampus/1.0 (sistema de caja de un negocio)"},
            )
    except httpx.HTTPError:
        # Sin internet, lento o caído: no es un error que deba detener la
        # carga de inventario.
        return None

    if respuesta.status_code != 200:
        return None

    try:
        datos = respuesta.json()
    except ValueError:
        return None

    if datos.get("status") != 1:
        return None

    return _armar_nombre(datos.get("product", {}))
