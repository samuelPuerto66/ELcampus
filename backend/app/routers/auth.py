from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import crear_token, solo_admin, usuario_actual
from ..config import hash_del_codigo_admin
from ..database import get_db
from ..security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["sesión"])


def buscar_usuario(quien: str, db: Session) -> models.Usuario | None:
    """Encuentra la cuenta por nombre o por correo, lo que haya escrito.

    El correo no distingue mayúsculas; el nombre de usuario sí, porque es
    como quedó escrito al registrarlo.
    """
    quien = quien.strip()
    return db.scalar(
        select(models.Usuario).where(
            (models.Usuario.nombre == quien)
            | (models.Usuario.correo == quien.lower())
        )
    )


def _iniciar(
    quien: str, clave: str, db: Session, codigo: str | None = None
) -> schemas.Sesion:
    usuario = buscar_usuario(quien, db)
    if usuario is None or not verify_password(clave, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre, correo o clave incorrectos.",
        )
    if not usuario.activo:
        raise HTTPException(status_code=403, detail="Este usuario está desactivado.")

    # Puerta extra para los administradores: además de su clave, el código
    # que solo ellos conocen. Se verifica aquí, en el servidor; lo que haga
    # la pantalla es solo comodidad.
    if usuario.rol is models.RolUsuario.administrador:
        guardado = hash_del_codigo_admin()
        if guardado is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "El código de administrador no está configurado. "
                    "Ejecuta codigo_admin.py en el servidor para ponerlo."
                ),
            )
        if not codigo or not verify_password(codigo, guardado):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Código de administrador incorrecto.",
            )

    return schemas.Sesion(
        access_token=crear_token(usuario),
        id=usuario.id,
        nombre=usuario.nombre,
        rol=usuario.rol,
    )


@router.post("/login", response_model=schemas.Sesion)
def login(datos: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Entrada estándar — la usa el botón Authorize de /docs.

    El formulario de OAuth2 no tiene dónde meter el código, así que por aquí
    un administrador no puede entrar: que use la pantalla de la app.
    """
    return _iniciar(datos.username, datos.password, db)


@router.post("/entrar", response_model=schemas.Sesion)
def entrar(datos: schemas.Credenciales, db: Session = Depends(get_db)):
    """Entrada en JSON — la usa la pantalla de login de la app."""
    return _iniciar(datos.nombre, datos.clave, db, datos.codigo)


@router.get("/yo", response_model=schemas.UsuarioLeer)
def yo(usuario: models.Usuario = Depends(usuario_actual)):
    return usuario


@router.get("/usuarios", response_model=list[schemas.UsuarioLeer])
def listar_usuarios(
    db: Session = Depends(get_db), _: models.Usuario = Depends(solo_admin)
):
    return db.scalars(select(models.Usuario)).all()


@router.post("/usuarios", response_model=schemas.UsuarioLeer, status_code=201)
def crear_usuario(
    datos: schemas.UsuarioCrear,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    nombre = datos.nombre.strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="El nombre no puede ir vacío.")
    if len(datos.clave) < 6:
        raise HTTPException(
            status_code=422, detail="La clave debe tener al menos 6 caracteres."
        )
    if db.scalar(select(models.Usuario).where(models.Usuario.nombre == nombre)):
        raise HTTPException(status_code=409, detail="Ya hay un usuario con ese nombre.")

    correo = datos.correo.lower() if datos.correo else None
    if correo and db.scalar(
        select(models.Usuario).where(models.Usuario.correo == correo)
    ):
        raise HTTPException(status_code=409, detail="Ya hay un usuario con ese correo.")

    usuario = models.Usuario(
        nombre=nombre,
        correo=correo,
        rol=datos.rol,
        password_hash=hash_password(datos.clave),
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/usuarios/{usuario_id}", response_model=schemas.UsuarioLeer)
def editar_usuario(
    usuario_id: int,
    datos: schemas.UsuarioEditar,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin),
):
    """Cambiar correo, rol, clave o si está activo. Solo llega lo que cambia."""
    usuario = db.get(models.Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Un administrador no puede quitarse a sí mismo del cargo ni apagarse:
    # dejaría el negocio sin quién administre.
    if usuario.id == admin.id:
        if datos.activo is False:
            raise HTTPException(
                status_code=400, detail="No puedes desactivarte a ti mismo."
            )
        if datos.rol is not None and datos.rol is not models.RolUsuario.administrador:
            raise HTTPException(
                status_code=400, detail="No puedes quitarte el rol de administrador."
            )

    if datos.correo is not None:
        correo = datos.correo.lower()
        ya_esta = db.scalar(
            select(models.Usuario).where(
                models.Usuario.correo == correo, models.Usuario.id != usuario_id
            )
        )
        if ya_esta:
            raise HTTPException(
                status_code=409, detail="Ya hay un usuario con ese correo."
            )
        usuario.correo = correo

    if datos.rol is not None:
        usuario.rol = datos.rol

    if datos.clave is not None:
        if len(datos.clave) < 6:
            raise HTTPException(
                status_code=422, detail="La clave debe tener al menos 6 caracteres."
            )
        usuario.password_hash = hash_password(datos.clave)

    if datos.activo is not None:
        usuario.activo = datos.activo

    db.commit()
    db.refresh(usuario)
    return usuario


@router.post("/usuarios/{usuario_id}/desactivar", response_model=schemas.UsuarioLeer)
def desactivar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: models.Usuario = Depends(solo_admin),
):
    usuario = db.get(models.Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if usuario.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo.")

    usuario.activo = False
    db.commit()
    db.refresh(usuario)
    return usuario
