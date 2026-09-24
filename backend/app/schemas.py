from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator

from .models import (
    EstadoCierreCaja,
    EstadoPedidoMesa,
    MetodoPago,
    RolUsuario,
    TipoCobro,
    TipoPlato,
    TipoVenta,
)

# --------------------------------------------------------------- sesión


class Credenciales(BaseModel):
    # En "nombre" puede venir el nombre de usuario o el correo: el servidor
    # busca por los dos. El código solo lo exigen las cuentas de administrador.
    nombre: str
    clave: str
    codigo: str | None = None


class Sesion(BaseModel):
    access_token: str
    token_type: str = "bearer"
    id: int
    nombre: str
    rol: RolUsuario


class UsuarioCrear(BaseModel):
    nombre: str
    rol: RolUsuario
    clave: str
    correo: EmailStr | None = None


class UsuarioEditar(BaseModel):
    """Todo opcional: se manda solo lo que se quiere cambiar."""

    correo: EmailStr | None = None
    rol: RolUsuario | None = None
    clave: str | None = None
    activo: bool | None = None


class UsuarioLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    correo: str | None
    rol: RolUsuario
    activo: bool


# ------------------------------------------------------------ productos


class ProductoBase(BaseModel):
    codigo_barras: str
    nombre: str
    precio: float
    tipo_venta: TipoVenta = TipoVenta.unidad
    precio_por_kg: float | None = None
    unidades_por_paquete: int = 1
    categoria: str | None = None
    alerta_minima: float = 5


class ProductoCrear(ProductoBase):
    stock_actual: float = 0


class ProductoActualizar(BaseModel):
    nombre: str | None = None
    precio: float | None = None
    precio_por_kg: float | None = None
    categoria: str | None = None
    alerta_minima: float | None = None


class ProductoLeer(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_actual: float
    precio_de_venta: float


# --------------------------------------------------------------- platos


class PlatoBase(BaseModel):
    nombre: str
    precio: float
    tipo: TipoPlato = TipoPlato.fijo
    activo_desde: date | None = None
    activo_hasta: date | None = None


class PlatoCrear(PlatoBase):
    pass


class PlatoActualizar(BaseModel):
    nombre: str | None = None
    precio: float | None = None
    activo_desde: date | None = None
    activo_hasta: date | None = None


class PlatoLeer(PlatoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# --------------------------------------------------------------- ventas


class ItemVenta(BaseModel):
    producto_id: int | None = None
    plato_id: int | None = None
    cantidad: float

    @model_validator(mode="after")
    def validar(self):
        if (self.producto_id is None) == (self.plato_id is None):
            raise ValueError("Cada ítem debe traer producto_id o plato_id, no ambos ni ninguno")
        if self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero")
        return self


class VentaCrear(BaseModel):
    tipo: TipoCobro
    metodo_pago: MetodoPago
    mesa: int | None = None
    items: list[ItemVenta]


class VentaDesdePedido(BaseModel):
    metodo_pago: MetodoPago


class VentaAnular(BaseModel):
    motivo: str


class DetalleVentaLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int | None
    plato_id: int | None
    nombre: str
    cantidad: float
    precio_unitario: float
    subtotal: float


class VentaLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora: datetime
    tipo: TipoCobro
    mesa: int | None
    total: float
    metodo_pago: MetodoPago
    vendedor_id: int
    anulada: bool
    motivo_anulacion: str | None
    detalles: list[DetalleVentaLeer]


# -------------------------------------------------------- pedidos de mesa


class PedidoCrear(BaseModel):
    mesa: int


class PedidoEnviar(BaseModel):
    """Un pedido completo saliendo del celular del mesero.

    La mesa se ocupa en el momento en que llega esto, no antes: mientras el
    mesero está anotando, el pedido vive solo en su teléfono.
    """

    mesa: int
    items: list["ItemPedidoCrear"]


class ItemPedidoCrear(BaseModel):
    producto_id: int | None = None
    plato_id: int | None = None
    cantidad: float = 1
    notas: str | None = None

    @model_validator(mode="after")
    def validar(self):
        if (self.producto_id is None) == (self.plato_id is None):
            raise ValueError("Cada ítem debe traer producto_id o plato_id, no ambos ni ninguno")
        if self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero")
        return self


class ItemPedidoCantidad(BaseModel):
    cantidad: float


class DetallePedidoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int | None
    plato_id: int | None
    nombre: str
    cantidad: float
    precio_unitario: float
    subtotal: float
    notas: str | None


class PedidoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mesa: int
    estado: EstadoPedidoMesa
    mesero_id: int
    hora_apertura: datetime
    hora_cuenta_pedida: datetime | None
    venta_id: int | None
    total: float
    detalles: list[DetallePedidoLeer]


# ----------------------------------------------------------- inventario


class EntradaMercancia(BaseModel):
    """Lo que entra SUMA al stock que ya había, nunca lo reemplaza."""

    producto_id: int
    cantidad: float


class AjusteStock(BaseModel):
    """Corrección de conteo: aquí sí se fija el número exacto."""

    producto_id: int
    stock_real: float
    motivo: str


class MovimientoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    producto_id: int
    tipo: str
    cantidad: float
    fecha: datetime
    usuario_id: int


# ----------------------------------------------------------------- caja


class AbrirCaja(BaseModel):
    base_inicial: float


class CerrarCaja(BaseModel):
    efectivo_contado: float


class CierreCajaLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    hora_apertura: datetime
    hora_cierre: datetime | None
    base_inicial: float
    efectivo_esperado: float | None
    efectivo_contado: float | None
    diferencia: float | None
    usuario_id: int
    estado: EstadoCierreCaja


# ------------------------------------------------------------- reportes


class VentasPorMetodo(BaseModel):
    metodo_pago: MetodoPago
    total: float
    cantidad: int


class ProductoVendido(BaseModel):
    nombre: str
    cantidad: float
    total: float


class ResumenDia(BaseModel):
    fecha: date
    total: float
    cantidad_ventas: int
    ticket_promedio: float
    mesas_atendidas: int
    por_metodo: list[VentasPorMetodo]
    mas_vendidos: list[ProductoVendido]
