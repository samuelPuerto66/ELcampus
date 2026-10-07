from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .models import (
    EstadoCierreCaja,
    EstadoCocina,
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
    costo: float | None = None
    es_insumo: bool = False


class ProductoCrear(ProductoBase):
    stock_actual: float = 0

    @model_validator(mode="after")
    def validar(self):
        if not self.nombre.strip():
            raise ValueError("El producto necesita un nombre")
        if not self.codigo_barras.strip():
            raise ValueError("El producto necesita un código")
        if self.tipo_venta is TipoVenta.peso:
            if self.precio_por_kg is None or self.precio_por_kg <= 0:
                raise ValueError("Un producto por peso necesita su precio por kilo")
        elif self.precio <= 0:
            raise ValueError("El precio tiene que ser mayor que cero")
        if self.costo is not None and self.costo < 0:
            raise ValueError("El costo no puede ser negativo")
        return self


class ProductoActualizar(BaseModel):
    nombre: str | None = None
    precio: float | None = Field(default=None, gt=0)
    precio_por_kg: float | None = Field(default=None, gt=0)
    categoria: str | None = None
    alerta_minima: float | None = None
    costo: float | None = Field(default=None, ge=0)
    es_insumo: bool | None = None


class ProductoLeer(ProductoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_actual: float
    precio_de_venta: float


class ConsultaCodigo(BaseModel):
    """Lo que se sabe de un código antes de registrarlo."""

    codigo_barras: str
    registrado: ProductoLeer | None = None
    nombre_sugerido: str | None = None


# --------------------------------------------------------------- platos


class PlatoBase(BaseModel):
    nombre: str
    precio: float = Field(gt=0)
    tipo: TipoPlato = TipoPlato.fijo
    activo_desde: date | None = None
    activo_hasta: date | None = None
    costo: float | None = None


class PlatoCrear(PlatoBase):
    pass


class PlatoActualizar(BaseModel):
    nombre: str | None = None
    precio: float | None = Field(default=None, gt=0)
    activo_desde: date | None = None
    activo_hasta: date | None = None
    costo: float | None = None


class InsumoEscribir(BaseModel):
    producto_id: int
    cantidad: float

    @model_validator(mode="after")
    def validar(self):
        if self.cantidad <= 0:
            raise ValueError("La cantidad del insumo debe ser mayor que cero")
        return self


class InsumoLeer(BaseModel):
    producto_id: int
    nombre: str
    cantidad: float
    costo_unitario: float | None
    costo_total: float | None


class RecetaLeer(BaseModel):
    plato_id: int
    nombre: str
    precio: float
    insumos: list[InsumoLeer]
    # None cuando a algún insumo le falta el costo: la receta está
    # incompleta y el margen todavía no se puede saber.
    costo: float | None
    utilidad: float | None


class PlatoLeer(PlatoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # El costo real: el de la receta si la tiene, el escrito a mano si no.
    costo_efectivo: float | None = None
    tiene_receta: bool = False


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


class PagoCrear(BaseModel):
    metodo: MetodoPago
    monto: float

    @model_validator(mode="after")
    def validar(self):
        if self.metodo is MetodoPago.mixto:
            raise ValueError("Cada pago va con un método concreto, no 'mixto'")
        if self.monto <= 0:
            raise ValueError("Cada pago tiene que ser mayor que cero")
        return self


class Cobro(BaseModel):
    """Cómo se paga una cuenta, venga del mostrador o de una mesa.

    Lo normal es mandar solo `metodo_pago`: todo por un mismo lado. Si el
    cliente divide (mitad efectivo, mitad Nequi), se mandan los `pagos` y
    tienen que sumar exacto lo que se cobra.
    """

    metodo_pago: MetodoPago | None = None
    pagos: list[PagoCrear] | None = None

    descuento: float = 0
    motivo_descuento: str | None = None
    # El código de administrador, solo cuando el descuento pasa del límite
    # que el vendedor puede dar solo.
    codigo_autorizacion: str | None = None

    propina: float = 0

    # A quién se le fía la parte que va por "fiado", si hay.
    cliente_fiado_id: int | None = None

    @model_validator(mode="after")
    def validar_cobro(self):
        if not self.pagos and self.metodo_pago is None:
            raise ValueError("Falta decir cómo pagó el cliente")
        if self.metodo_pago is MetodoPago.mixto and not self.pagos:
            raise ValueError("Para un pago mixto hay que decir cuánto va por cada método")
        if self.descuento < 0:
            raise ValueError("El descuento no puede ser negativo")
        if self.propina < 0:
            raise ValueError("La propina no puede ser negativa")
        return self


class VentaCrear(Cobro):
    tipo: TipoCobro
    mesa: int | None = None
    items: list[ItemVenta]
    # Si la venta lleva platos, van a la cocina para llevar a este nombre.
    nombre_para_llevar: str | None = Field(default=None, max_length=60)


class VentaDesdePedido(Cobro):
    # Lo que la caja le mostró al cliente. Si la mesa cambió entre que el
    # cajero miró la cuenta y le dio a cobrar, el servidor no cobra a
    # ciegas: avisa para que el cliente pague lo que de verdad pidió.
    total_esperado: float | None = None


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


class PagoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metodo: MetodoPago
    monto: float


class VentaLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora: datetime
    tipo: TipoCobro
    mesa: int | None
    subtotal: float
    descuento: float
    motivo_descuento: str | None
    total: float
    propina: float
    a_cobrar: float
    metodo_pago: MetodoPago
    pagos: list[PagoLeer]
    cliente_fiado_id: int | None
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

    mesa: int = Field(gt=0)
    items: list["ItemPedidoCrear"]
    # La inventa el celular, una por pedido. Si el mismo pedido llega dos
    # veces porque el WiFi se cayó a mitad de camino, la segunda se ignora.
    clave: str | None = Field(default=None, max_length=64)


class ItemPedidoCrear(BaseModel):
    producto_id: int | None = None
    plato_id: int | None = None
    cantidad: float = 1
    # Para la cocina: "sin cebolla", "bien asado". Una nota en blanco es
    # lo mismo que no tener nota.
    notas: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validar(self):
        if (self.producto_id is None) == (self.plato_id is None):
            raise ValueError("Cada ítem debe traer producto_id o plato_id, no ambos ni ninguno")
        if self.cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor que cero")
        self.notas = (self.notas or "").strip() or None
        return self


class QuitarItem(BaseModel):
    """Quitar de una mesa algo que ya se había enviado."""

    cantidad: float = Field(gt=0)
    motivo: str = Field(max_length=200)
    # Solo cuando la corrección no la puede hacer el mesero por su cuenta.
    codigo_autorizacion: str | None = None

    @model_validator(mode="after")
    def validar(self):
        self.motivo = self.motivo.strip()
        if not self.motivo:
            raise ValueError("Escribe por qué se quita: queda en el historial")
        return self


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
    estado_cocina: EstadoCocina
    # Quién mandó lo último de esta línea. La pantalla lo usa para saber de
    # antemano si una corrección va a pedir el código del administrador.
    agregado_por_id: int | None


class ItemComanda(BaseModel):
    """Una línea como la ve la cocina: qué, cuánto, para qué mesa."""

    id: int
    pedido_id: int
    mesa: int
    para_llevar: bool
    nombre_cliente: str | None
    nombre: str
    cantidad: float
    notas: str | None
    estado_cocina: EstadoCocina
    creado_en: datetime


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
    base_inicial: float = Field(ge=0)


class CerrarCaja(BaseModel):
    efectivo_contado: float = Field(ge=0)


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
    usuario_nombre: str
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
    # Cuánta plata entró por cada lado, propinas incluidas: es lo que tiene
    # que aparecer en el cajón, en Nequi o en el datáfono.
    por_metodo: list[VentasPorMetodo]
    mas_vendidos: list[ProductoVendido]

    # Lo vendido menos lo que costó comprarlo. `lineas_sin_costo` dice de
    # cuántas líneas no se sabe el costo: mientras ese número no sea cero,
    # la utilidad es un piso, no la cifra real.
    costo: float
    utilidad: float
    margen_porcentaje: float | None
    lineas_sin_costo: int

    # Lo que se regaló o se rebajó, y lo que dejaron de propina para los
    # empleados. Ninguna de las dos cosas es plata del negocio.
    descuentos: float
    cantidad_descuentos: int
    propinas: float

    # Fiado: lo que se vendió hoy sin que entrara plata, lo que trajeron
    # hoy para pagar deudas, y cuánto le deben al negocio en total.
    fiado_del_dia: float
    abonos_del_dia: float
    te_deben: float


class Novedad(BaseModel):
    """Algo que alguien hizo con la plata y que el dueño debe poder ver."""

    # El número de la venta, o el de la corrección si es una corrección.
    id: int
    hora: datetime
    quien: str
    monto: float
    motivo: str | None
    con_codigo: bool = False
    # Solo en las correcciones: qué se quitó y de qué mesa.
    que: str | None = None


class NovedadesDia(BaseModel):
    fecha: date
    anulaciones: list[Novedad]
    descuentos: list[Novedad]
    # Lo que se quitó de una mesa después de enviarlo: qué y cuánto valía.
    correcciones: list[Novedad]


# ------------------------------------------------------------------ fiado


class ClienteFiadoCrear(BaseModel):
    nombre: str = Field(max_length=120)
    telefono: str | None = Field(default=None, max_length=40)
    # Hasta cuánto puede deber. Sin cupo, no hay límite.
    cupo: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validar(self):
        self.nombre = self.nombre.strip()
        if not self.nombre:
            raise ValueError("El cliente necesita un nombre")
        self.telefono = (self.telefono or "").strip() or None
        return self


class ClienteFiadoEditar(BaseModel):
    """Todo opcional: se manda solo lo que cambia. Para quitar el cupo se
    manda `cupo: null` explícito."""

    telefono: str | None = Field(default=None, max_length=40)
    cupo: float | None = Field(default=None, ge=0)
    activo: bool | None = None


class ClienteFiadoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    telefono: str | None
    cupo: float | None
    activo: bool
    # Lo que debe hoy. Se calcula, no se guarda.
    saldo: float = 0


class MovimientoFiado(BaseModel):
    """Una línea de la cuenta de un cliente: algo que se llevó fiado, o
    plata que trajo."""

    tipo: str  # "fiado" o "abono"
    id: int  # el número de la venta o del abono
    fecha: datetime
    monto: float
    detalle: str
    anulado: bool


class ClienteFiadoDetalle(ClienteFiadoLeer):
    movimientos: list[MovimientoFiado]


class AbonoCrear(BaseModel):
    monto: float = Field(gt=0)
    metodo: MetodoPago = MetodoPago.efectivo

    @model_validator(mode="after")
    def validar(self):
        if self.metodo in (MetodoPago.fiado, MetodoPago.mixto):
            raise ValueError("Un abono se paga con plata: efectivo, Nequi, Daviplata o tarjeta")
        return self


class AbonoLeer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente_id: int
    monto: float
    metodo: MetodoPago
    fecha: datetime
    anulado: bool


class AbonoAnular(BaseModel):
    motivo: str = Field(max_length=200)
