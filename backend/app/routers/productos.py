from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import caja, solo_admin, usuario_actual
from ..catalogo_externo import buscar_nombre
from ..database import get_db

router = APIRouter(prefix="/productos", tags=["productos"])


@router.get("", response_model=list[schemas.ProductoLeer])
def listar_productos(
    buscar: str | None = None,
    categoria: str | None = None,
    incluir_insumos: bool = False,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    """Por defecto solo lo que se vende.

    Los insumos de cocina se controlan en inventario pero no tienen por qué
    aparecerle al mesero en el menú ni al vendedor en la caja.
    """
    consulta = select(models.Producto).order_by(models.Producto.nombre)
    if not incluir_insumos:
        consulta = consulta.where(models.Producto.es_insumo.is_(False))
    if buscar:
        consulta = consulta.where(models.Producto.nombre.ilike(f"%{buscar}%"))
    if categoria:
        consulta = consulta.where(models.Producto.categoria == categoria)
    return db.scalars(consulta).all()


@router.get("/codigo/{codigo_barras}", response_model=schemas.ProductoLeer)
def buscar_por_codigo_barras(
    codigo_barras: str,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    producto = db.scalar(
        select(models.Producto).where(models.Producto.codigo_barras == codigo_barras)
    )
    if producto is None:
        raise HTTPException(
            status_code=404, detail="Ese código no está registrado todavía."
        )
    if producto.es_insumo:
        raise HTTPException(
            status_code=409,
            detail=f"{producto.nombre} es un insumo de cocina, no se vende suelto.",
        )
    return producto


@router.get("/consultar/{codigo_barras}", response_model=schemas.ConsultaCodigo)
async def consultar_codigo(
    codigo_barras: str,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(caja),
):
    """Para cargar inventario: ¿este código ya está, y cómo se llama?

    Si no está registrado, se le pregunta el nombre a Open Food Facts para
    ahorrar tecleo. Que no lo conozca es normal, no un error.
    """
    registrado = db.scalar(
        select(models.Producto).where(models.Producto.codigo_barras == codigo_barras)
    )
    if registrado is not None:
        return schemas.ConsultaCodigo(codigo_barras=codigo_barras, registrado=registrado)

    return schemas.ConsultaCodigo(
        codigo_barras=codigo_barras,
        registrado=None,
        nombre_sugerido=await buscar_nombre(codigo_barras),
    )


@router.get("/{producto_id}", response_model=schemas.ProductoLeer)
def obtener_producto(
    producto_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(usuario_actual),
):
    producto = db.get(models.Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


@router.post("", response_model=schemas.ProductoLeer, status_code=201)
def crear_producto(
    datos: schemas.ProductoCrear,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(caja),
):
    existente = db.scalar(
        select(models.Producto).where(
            models.Producto.codigo_barras == datos.codigo_barras
        )
    )
    if existente is not None:
        raise HTTPException(
            status_code=409, detail="Ese código de barras ya está registrado"
        )

    producto = models.Producto(**datos.model_dump())
    db.add(producto)
    db.commit()
    db.refresh(producto)
    return producto


@router.patch("/{producto_id}", response_model=schemas.ProductoLeer)
def actualizar_producto(
    producto_id: int,
    datos: schemas.ProductoActualizar,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(solo_admin),
):
    """Cambiar precio o categoría. El stock no se toca aquí: se mueve por
    entradas de mercancía o por un ajuste de conteo, que dejan rastro."""
    producto = db.get(models.Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(producto, campo, valor)

    db.commit()
    db.refresh(producto)
    return producto
