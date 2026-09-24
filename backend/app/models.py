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


class Venta(Base):
    __tablename__ = "ventas"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Hora local, no UTC: una venta del sábado 8pm en Colombia (UTC-5) caería
    # en el domingo si se guardara en UTC, y el reporte del día no cuadraría.
    fecha_hora: Mapped[datetime] = mapped_column(default=datetime.now)
    tipo: Mapped[TipoCobro] = mapped_column(SAEnum(TipoCobro))
    mesa: Mapped[int | None] = mapped_column(default=None)
    total: Mapped[float]
    metodo_pago: Mapped[MetodoPago] = mapped_column(SAEnum(MetodoPago))
    vendedor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))

    # Anulación: nunca se borra una venta, se marca. Así el historial de
    # auditoría y el cuadre de caja siempre cuadran con lo que pasó de verdad.
    anulada: Mapped[bool] = mapped_column(default=False)
    motivo_anulacion: Mapped[str | None] = mapped_column(default=None)
    anulada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), default=None)
    anulada_en: Mapped[datetime | None] = mapped_column(default=None)

    # Placeholder para cuando se confirme si aplica facturación electrónica DIAN.
    factura_electronica_id: Mapped[str | None] = mapped_column(String(100), default=None)

    vendedor: Mapped["Usuario"] = relationship(foreign_keys=[vendedor_id])
    detalles: Mapped[list["DetalleVenta"]] = relationship(back_populates="venta")


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


class PedidoMesa(Base):
    __tablename__ = "pedidos_mesa"

    id: Mapped[int] = mapped_column(primary_key=True)
    mesa: Mapped[int]
    estado: Mapped[EstadoPedidoMesa] = mapped_column(SAEnum(EstadoPedidoMesa), default=EstadoPedidoMesa.abierto)
    mesero_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    hora_apertura: Mapped[datetime] = mapped_column(default=datetime.now)
    hora_cuenta_pedida: Mapped[datetime | None] = mapped_column(default=None)
    venta_id: Mapped[int | None] = mapped_column(ForeignKey("ventas.id"), default=None)

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

    pedido: Mapped["PedidoMesa"] = relationship(back_populates="detalles")
    producto: Mapped["Producto | None"] = relationship()
    plato: Mapped["Plato | None"] = relationship()

    @property
    def nombre(self) -> str:
        return self.producto.nombre if self.producto is not None else self.plato.nombre

    @property
    def precio_unitario(self) -> float:
        if self.producto is not None:
            return self.producto.precio_de_venta
        return self.plato.precio

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


class MovimientoInventario(Base):
    __tablename__ = "movimientos_inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id"))
    tipo: Mapped[TipoMovimientoInventario] = mapped_column(SAEnum(TipoMovimientoInventario))
    cantidad: Mapped[float]
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))


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
