from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import ALGORITMO, HORAS_DE_SESION, SECRET_KEY
from .database import get_db
from .models import RolUsuario, Usuario

esquema_token = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def crear_token(usuario: Usuario) -> str:
    vence = datetime.now(timezone.utc) + timedelta(hours=HORAS_DE_SESION)
    return jwt.encode(
        {
            "sub": str(usuario.id),
            "rol": usuario.rol.value,
            "nombre": usuario.nombre,
            "exp": vence,
        },
        SECRET_KEY,
        algorithm=ALGORITMO,
    )


def leer_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITMO])


def usuario_actual(
    token: str = Depends(esquema_token), db: Session = Depends(get_db)
) -> Usuario:
    no_autorizado = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Tu sesión venció. Vuelve a entrar.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        datos = leer_token(token)
    except jwt.PyJWTError:
        raise no_autorizado

    usuario = db.get(Usuario, int(datos["sub"]))
    if usuario is None or not usuario.activo:
        raise no_autorizado
    return usuario


def exigir_rol(*roles: RolUsuario):
    """El administrador puede hacer todo lo que puedan los demás."""

    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol is RolUsuario.administrador or usuario.rol in roles:
            return usuario
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu rol no tiene permiso para hacer esto.",
        )

    return dependencia


solo_admin = exigir_rol()
caja = exigir_rol(RolUsuario.vendedor)
salon = exigir_rol(RolUsuario.vendedor, RolUsuario.mesero)
# El mesero también marca platos listos cuando él mismo los recoge.
cocina = exigir_rol(RolUsuario.cocina, RolUsuario.vendedor, RolUsuario.mesero)
