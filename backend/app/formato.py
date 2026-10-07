"""Cómo se escriben las cifras en los mensajes para la gente del negocio."""


def plata(valor: float) -> str:
    """$59.200, como se escribe en Colombia."""
    return "$" + f"{round(valor):,}".replace(",", ".")
