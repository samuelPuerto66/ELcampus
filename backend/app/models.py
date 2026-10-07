import enum
from datetime import datetime, date

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class RolUsuario(str, enum.Enum):
    administrador = "administrador"
    vendedor = "vendedor"
    mesero = "mesero"
    cocina = "cocina"


class EstadoCocina(str, enum.Enum):
    pendiente = "pendiente"
    listo = "listo"


class TipoVenta(str, enum.Enum):
    unidad = "unidad"
    peso = "peso"


class TipoPlato(str, enum.Enum):
    fijo = "fijo"
    especial = "especial"


class TipoCobro(str, enum.Enum):
    mostrador = "mostrador"
    restaurante = "restaurante"


class MetodoPago(str, enum.Enum):
    efectivo = "efectivo"
    nequi = "nequi"
    daviplata = "daviplata"
    tarjeta = "tarjeta"
    # La plata no entró: el cliente quedó debiendo. Ver ClienteFiado.
    fiado = "fiado"
    # Solo como resumen en la venta: el cliente pagó con más de un método.
    # El detalle de cuánto entró por cada uno vive en PagoVenta.
    mixto = "mixto"


class EstadoPedidoMesa(str, enum.Enum):
    abierto = "abierto"
    cuenta_pedida = "cuenta_pedida"
    pagado = "pagado"


class TipoMovimientoInventario(str, enum.Enum):
    entrada = "entrada"
    salida = "salida"


class EstadoCierreCaja(str, enum.Enum):
    abierto = "abierto"
    cerrado = "cerrado"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    # El correo es opcional: el mesero entra con su nombre y ya. Sirve para
    # quien prefiera escribirlo, y se guarda siempre en minúsculas.
    correo: Mapped[str | None] = mapped_column(
        String(180), unique=True, index=True, default=None
    )
    rol: Mapped[RolUsuario] = mapped_column(SAEnum(RolUsuario))
    password_hash: Mapped[str] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(default=True)


class Producto(Base):
    __tablename__ = "productos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_barras: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    # Para tipo_venta == unidad: precio es el precio por unidad/paquete.
    # Para tipo_venta == peso: precio_por_kg manda, precio queda como referencia opcional.
    precio: Mapped[float]
    tipo_venta: Mapped[TipoVenta] = mapped_column(SAEnum(TipoVenta), default=TipoVenta.unidad)
    precio_por_kg: Mapped[float | None] = mapped_column(default=None)
    unidades_por_paquete: Mapped[int] = mapped_column(default=1)
    stock_actual: Mapped[float] = mapped_column(default=0)
    categoria: Mapped[str | None] = mapped_column(String(100), default=None)
    alerta_minima: Mapped[float] = mapped_column(default=5)
    # Lo que cuesta comprarlo, en la misma unidad en que se vende. Sin esto
    # el sistema solo sabe cuánto se vendió, nunca cuánto se ganó.
    costo: Mapped[float | None] = mapped_column(default=None)
    # Un insumo (la carne, el chorizo) se controla en inventario pero no se
    # vende suelto: no aparece en la caja ni en el menú del mesero.
    es_insumo: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        CheckConstraint(
            "(tipo_venta = 'unidad') OR (tipo_venta = 'peso' AND precio_por_kg IS NOT NULL)",
            name="ck_producto_precio_por_kg_si_es_peso",
        ),
    )

    @property
    def precio_de_venta(self) -> float:
        """Lo que se cobra por unidad — o por kilo si el producto va por peso."""
        if self.tipo_venta == TipoVenta.peso:
            return self.precio_por_kg
        return self.precio


class Plato(Base):
    __tablename__ = "platos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    precio: Mapped[float]
    tipo: Mapped[TipoPlato] = mapped_column(SAEnum(TipoPlato))
    activo_desde: Mapped[date | None] = mapped_column(default=None)
    activo_hasta: Mapped[date | None] = mapped_column(default=None)
    # Costo a ojo, para platos sin receta. Si el plato tiene receta, el
    # costo sale de sus insumos y este número se ignora.
    costo: Mapped[float | None] = mapped_column(default=None)

    insumos: Mapped[list["InsumoPlato"]] = relationship(
        back_populates="plato", cascade="all, delete-orphan"
    )

    @property
    def tiene_receta(self) -> bool:
        return len(self.insumos) > 0

    @property
    def costo_efectivo(self) -> float | None:
        """Lo que cuesta preparar el plato.

        Con receta sale de los insumos; sin receta, del número que escribió
        el administrador. Si a un insumo le falta el costo se devuelve None
        en vez de una cifra a medias: una utilidad inventada es peor que
        una que se declara incompleta.
        """
        if not self.insumos:
            return self.costo

        total = 0.0
        for insumo in self.insumos:
            if insumo.producto.costo is None:
                return None
            total += insumo.cantidad * insumo.producto.costo
        return float(round(total))


class InsumoPlato(Base):
    """Qué lleva un plato y cuánto. La receta.

    Es lo que permite que vender una picada descuente la carne y el
    chorizo, y que el costo del plato se calcule solo en vez de adivinarse.
    """

    __tablename__ = "insumos_plato"

    id: Mapped[int] = mapped_column(primary_key=True)
    plato_id: Mapped[int] = mapped_column(ForeignKey("platos.id"))
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    # En la unidad del producto: kilos si va por peso, unidades si no.
    cantidad: Mapped[float]

    plato: Mapped["Plato"] = relationship(back_populates="insumos")
    producto: Mapped["Producto"] = relationship()


class Venta(Base):
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Hora local, no UTC: una venta del sábado 8pm en Colombia (UTC-5) caería
    # en el domingo si se guardara en UTC, y el reporte del día no cuadraría.
    fecha_hora: Mapped[datetime] = mapped_column(default=datetime.now)
    tipo: Mapped[TipoCobro] = mapped_column(SAEnum(TipoCobro))
    mesa: Mapped[int | None] = mapped_column(default=None)
    # Lo que el negocio cobró por lo vendido, ya con el descuento restado y
    # sin la propina. Es la cifra de ventas del día.
    total: Mapped[float]
    metodo_pago: Mapped[MetodoPago] = mapped_column(SAEnum(MetodoPago))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))

    # Descuento o cortesía. Queda escrito por qué y si hizo falta el código
    # de un administrador: regalar plata sin rastro es lo mismo que perderla.
    descuento: Mapped[float] = mapped_column(default=0)
    motivo_descuento: Mapped[str | None] = mapped_column(default=None)
    descuento_con_codigo: Mapped[bool] = mapped_column(default=False)

    # La propina es de los empleados, no del negocio: va aparte del total
    # para no inflar las ventas, pero sí entra al cajón si la dan en efectivo.
    propina: Mapped[float] = mapped_column(default=0)

    # A quién se le fió, si parte de la cuenta quedó fiada.
    cliente_fiado_id: Mapped[int | None] = mapped_column(
        ForeignKey("clientes_fiado.id"), default=None
    )

    # Anulación: nunca se borra una venta, se marca. Así el historial de
    # auditoría y el cuadre de caja siempre cuadran con lo que pasó de verdad.
    anulada: Mapped[bool] = mapped_column(default=False)
    motivo_anulacion: Mapped[str | None] = mapped_column(default=None)
    anulada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), default=None)
    anulada_en: Mapped[datetime | None] = mapped_column(default=None)

    # Placeholder para cuando se confirme si aplica facturación electrónica DIAN.
    factura_electronica_id: Mapped[str | None] = mapped_column(String(100), default=None)

    vendedor: Mapped["Usuario"] = relationship(foreign_keys=[vendedor_id])
    anulada_por: Mapped["Usuario | None"] = relationship(foreign_keys=[anulada_por_id])
    detalles: Mapped[list["DetalleVenta"]] = relationship(back_populates="venta")
    pagos: Mapped[list["PagoVenta"]] = relationship(
        back_populates="venta", cascade="all, delete-orphan"
    )

    @property
    def subtotal(self) -> float:
        """Lo que sumaban los productos antes del descuento."""
        return self.total + self.descuento

    @property
    def a_cobrar(self) -> float:
        """Lo que pagó el cliente en total: la cuenta más la propina."""
        return self.total + self.propina


class PagoVenta(Base):
    """Cuánto entró por cada método en una venta.

    Una venta normal tiene un solo pago. Si el cliente paga mitad en
    efectivo y mitad por Nequi, tiene dos, y el cuadre de caja cuenta solo
    la parte en efectivo: es la única que está en el cajón.
    """

    __tablename__ = "pagos_venta"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"), index=True)
    metodo: Mapped[MetodoPago] = mapped_column(SAEnum(MetodoPago))
    monto: Mapped[float]

    venta: Mapped["Venta"] = relationship(back_populates="pagos")


class DetalleVenta(Base):
    __tablename__ = "detalle_venta"

    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas.id"))
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), default=None)
    plato_id: Mapped[int | None] = mapped_column(ForeignKey("platos.id"), default=None)
    # cantidad es float para poder registrar pesos (ej. 0.350 kg de morraja).
    cantidad: Mapped[float]
    precio_unitario: Mapped[float]
    subtotal: Mapped[float]
    # El costo se congela aquí al cobrar. Si mañana sube el precio de la
    # cerveza, la utilidad de la venta de hoy no se reescribe sola.
    costo_unitario: Mapped[float | None] = mapped_column(default=None)

    venta: Mapped["Venta"] = relationship(back_populates="detalles")
    producto: Mapped["Producto | None"] = relationship()
    plato: Mapped["Plato | None"] = relationship()

    @property
    def nombre(self) -> str:
        return self.producto.nombre if self.producto is not None else self.plato.nombre

    __table_args__ = (
        CheckConstraint(
            "(producto_id IS NOT NULL AND plato_id IS NULL) OR "
            "(producto_id IS NULL AND plato_id IS NOT NULL)",
            name="ck_detalle_venta_producto_xor_plato",
        ),
    )


# Un pedido para llevar no ocupa ninguna mesa. Se guarda con este número
# solo porque la columna `mesa` no admite vacío; lo que manda es el campo
# `para_llevar`, y ninguna pantalla muestra una "mesa 0".
MESA_PARA_LLEVAR = 0


class PedidoMesa(Base):
    __tablename__ = "pedidos_mesa"

    id: Mapped[int] = mapped_column(primary_key=True)
    mesa: Mapped[int]
    estado: Mapped[EstadoPedidoMesa] = mapped_column(SAEnum(EstadoPedidoMesa), default=EstadoPedidoMesa.abierto)
    mesero_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    hora_apertura: Mapped[datetime] = mapped_column(default=datetime.now)
    hora_cuenta_pedida: Mapped[datetime | None] = mapped_column(default=None)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), default=None)

    # Platos vendidos en la caja para llevar. Se pagan antes de cocinarse,
    # así que nacen ya pagados; existen solo para que la cocina los vea.
    para_llevar: Mapped[bool] = mapped_column(default=False)
    # A nombre de quién, para llamarlo cuando esté listo.
    nombre_cliente: Mapped[str | None] = mapped_column(String(60), default=None)

    detalles: Mapped[list["DetallePedidoMesa"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )

    @property
    def total(self) -> float:
        return float(round(sum(detalle.subtotal for detalle in self.detalles)))


class DetallePedidoMesa(Base):
    __tablename__ = "detalle_pedido_mesa"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_mesa.id"))
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), default=None)
    plato_id: Mapped[int | None] = mapped_column(ForeignKey("platos.id"), default=None)
    cantidad: Mapped[float]
    notas: Mapped[str | None] = mapped_column(default=None)
    # El precio se congela cuando el cliente pide, no se lee al cobrar: si
    # el administrador sube un precio mientras la mesa está comiendo, esa
    # mesa paga lo que le dijeron, no lo nuevo.
    precio_unitario: Mapped[float]
    # Para la pantalla de cocina. Solo aplica a los platos: una cerveza no
    # se cocina. `creado_en` es lo que deja ver cuánto lleva esperando.
    estado_cocina: Mapped[EstadoCocina] = mapped_column(
        SAEnum(EstadoCocina), default=EstadoCocina.pendiente
    )
    creado_en: Mapped[datetime] = mapped_column(default=datetime.now)
    # Quién mandó lo último de esta línea, y cuándo. Es lo que decide si el
    # mesero puede corregirla solo o necesita a un administrador.
    agregado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), default=None
    )
    actualizado_en: Mapped[datetime | None] = mapped_column(default=None)

    pedido: Mapped["PedidoMesa"] = relationship(back_populates="detalles")
    producto: Mapped["Producto | None"] = relationship()
    plato: Mapped["Plato | None"] = relationship()

    @property
    def nombre(self) -> str:
        return self.producto.nombre if self.producto is not None else self.plato.nombre

    @property
    def subtotal(self) -> float:
        return float(round(self.cantidad * self.precio_unitario))

    __table_args__ = (
        CheckConstraint(
            "(producto_id IS NOT NULL AND plato_id IS NULL) OR "
            "(producto_id IS NULL AND plato_id IS NOT NULL)",
            name="ck_detalle_pedido_producto_xor_plato",
        ),
    )


class CorreccionPedido(Base):
    """Algo que se quitó de una mesa después de enviarlo a la caja.

    Quitar de la cuenta algo que el cliente sí consumió es otra forma de
    regalar plata, así que cada corrección queda escrita: qué, cuánto, quién
    y por qué. El dueño las ve en el resumen del día.
    """

    __tablename__ = "correcciones_pedido"

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_mesa.id"), index=True)
    # El nombre y el precio se copian: si después se borra el producto o
    # cambia el precio, el registro sigue diciendo lo que pasó.
    nombre: Mapped[str] = mapped_column(String(200))
    cantidad: Mapped[float]
    precio_unitario: Mapped[float]
    motivo: Mapped[str]
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    con_codigo: Mapped[bool] = mapped_column(default=False)
    hora: Mapped[datetime] = mapped_column(default=datetime.now)

    pedido: Mapped["PedidoMesa"] = relationship()
    usuario: Mapped["Usuario"] = relationship()

    @property
    def monto(self) -> float:
        return float(round(self.cantidad * self.precio_unitario))


class ClienteFiado(Base):
    """Alguien a quien el negocio le fía: el cuaderno de fiados.

    El cupo es hasta cuánto puede llegar a deber. Sin cupo (None) no hay
    límite; eso lo decide el dueño cliente por cliente.
    """

    __tablename__ = "clientes_fiado"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(40), default=None)
    cupo: Mapped[float | None] = mapped_column(default=None)
    # Apagar a un cliente no borra lo que debe: solo deja de fiársele.
    activo: Mapped[bool] = mapped_column(default=True)
    creado_en: Mapped[datetime] = mapped_column(default=datetime.now)


class AbonoFiado(Base):
    """Plata que un cliente trajo para pagar lo que debía.

    Un abono en efectivo entra al cajón, así que cuenta en el cuadre del
    turno igual que una venta. Por eso no se borra: si se registró mal, un
    administrador lo anula y queda el rastro.
    """

    __tablename__ = "abonos_fiado"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes_fiado.id"), index=True)
    monto: Mapped[float]
    metodo: Mapped[MetodoPago] = mapped_column(SAEnum(MetodoPago))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)

    anulado: Mapped[bool] = mapped_column(default=False)
    anulado_en: Mapped[datetime | None] = mapped_column(default=None)
    anulado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), default=None
    )
    motivo_anulacion: Mapped[str | None] = mapped_column(default=None)

    cliente: Mapped["ClienteFiado"] = relationship()
    usuario: Mapped["Usuario"] = relationship(foreign_keys=[usuario_id])


class EnvioMesa(Base):
    """Recibo de cada pedido que sube del celular del mesero.

    Si se cae el WiFi justo después de enviar, el celular no sabe si llegó y
    lo vuelve a mandar. Con la clave del envío el servidor reconoce que ya
    lo recibió y no lo suma dos veces: sin esto, una picada se vuelve dos.
    """

    __tablename__ = "envios_mesa"

    clave: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos_mesa.id"))
    creado_en: Mapped[datetime] = mapped_column(default=datetime.now)


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    tipo: Mapped[TipoMovimientoInventario] = mapped_column(SAEnum(TipoMovimientoInventario))
    cantidad: Mapped[float]
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    # De qué venta salió. Al anular, se devuelve exactamente lo que se
    # descontó — incluidos los insumos de un plato, aunque la receta haya
    # cambiado después.
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), default=None)


class CierreCaja(Base):
    __tablename__ = "cierres_caja"

    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date]
    hora_apertura: Mapped[datetime] = mapped_column(default=datetime.now)
    hora_cierre: Mapped[datetime | None] = mapped_column(default=None)
    base_inicial: Mapped[float]
    efectivo_esperado: Mapped[float | None] = mapped_column(default=None)
    efectivo_contado: Mapped[float | None] = mapped_column(default=None)
    diferencia: Mapped[float | None] = mapped_column(default=None)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    estado: Mapped[EstadoCierreCaja] = mapped_column(SAEnum(EstadoCierreCaja), default=EstadoCierreCaja.abierto)

    usuario: Mapped["Usuario"] = relationship()

    @property
    def usuario_nombre(self) -> str:
        return self.usuario.nombre
