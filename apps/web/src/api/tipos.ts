export type Rol = 'administrador' | 'vendedor' | 'mesero' | 'cocina'
export type EstadoCocina = 'pendiente' | 'listo'
/** 'fiado': la plata no entró, el cliente quedó debiendo. */
export type MetodoPago = 'efectivo' | 'nequi' | 'daviplata' | 'tarjeta' | 'fiado'
/** Lo que queda en la venta: 'mixto' cuando se pagó por más de un lado. */
export type MetodoDeVenta = MetodoPago | 'mixto'
export type TipoCobro = 'mostrador' | 'restaurante'
export type EstadoPedido = 'abierto' | 'cuenta_pedida' | 'pagado'

export interface Sesion {
  access_token: string
  token_type: string
  id: number
  nombre: string
  rol: Rol
}

export interface Usuario {
  id: number
  nombre: string
  correo: string | null
  rol: Rol
  activo: boolean
}

export interface Producto {
  id: number
  codigo_barras: string
  nombre: string
  precio: number
  tipo_venta: 'unidad' | 'peso'
  precio_por_kg: number | null
  precio_de_venta: number
  unidades_por_paquete: number
  stock_actual: number
  categoria: string | null
  alerta_minima: number
  costo: number | null
  es_insumo: boolean
}

export interface InsumoLeer {
  producto_id: number
  nombre: string
  cantidad: number
  costo_unitario: number | null
  costo_total: number | null
}

export interface RecetaLeer {
  plato_id: number
  nombre: string
  precio: number
  insumos: InsumoLeer[]
  costo: number | null
  utilidad: number | null
}

export interface ConsultaCodigo {
  codigo_barras: string
  registrado: Producto | null
  nombre_sugerido: string | null
}

export interface Plato {
  id: number
  nombre: string
  precio: number
  tipo: 'fijo' | 'especial'
  activo_desde: string | null
  activo_hasta: string | null
  costo: number | null
  costo_efectivo: number | null
  tiene_receta: boolean
}

export interface DetalleVenta {
  id: number
  producto_id: number | null
  plato_id: number | null
  nombre: string
  cantidad: number
  precio_unitario: number
  subtotal: number
}

export interface Pago {
  metodo: MetodoPago
  monto: number
}

export interface Venta {
  id: number
  fecha_hora: string
  tipo: TipoCobro
  mesa: number | null
  subtotal: number
  descuento: number
  motivo_descuento: string | null
  total: number
  propina: number
  a_cobrar: number
  metodo_pago: MetodoDeVenta
  pagos: Pago[]
  cliente_fiado_id: number | null
  vendedor_id: number
  anulada: boolean
  motivo_anulacion: string | null
  detalles: DetalleVenta[]
}

export interface DetallePedido extends DetalleVenta {
  notas: string | null
  estado_cocina: EstadoCocina
  /** Quién mandó lo último de esta línea. */
  agregado_por_id: number | null
}

export interface Pedido {
  id: number
  mesa: number
  estado: EstadoPedido
  mesero_id: number
  hora_apertura: string
  hora_cuenta_pedida: string | null
  venta_id: number | null
  total: number
  detalles: DetallePedido[]
}

export interface ItemComanda {
  id: number
  pedido_id: number
  mesa: number
  /** Vendido en la caja para llevar: no tiene mesa. */
  para_llevar: boolean
  nombre_cliente: string | null
  nombre: string
  cantidad: number
  notas: string | null
  estado_cocina: EstadoCocina
  creado_en: string
}

export interface TurnoCaja {
  id: number
  fecha: string
  hora_apertura: string
  hora_cierre: string | null
  base_inicial: number
  efectivo_esperado: number | null
  efectivo_contado: number | null
  diferencia: number | null
  usuario_id: number
  usuario_nombre: string
  estado: 'abierto' | 'cerrado'
}

export interface ResumenDia {
  fecha: string
  total: number
  cantidad_ventas: number
  ticket_promedio: number
  mesas_atendidas: number
  por_metodo: { metodo_pago: MetodoPago; total: number; cantidad: number }[]
  mas_vendidos: { nombre: string; cantidad: number; total: number }[]
  costo: number
  utilidad: number
  margen_porcentaje: number | null
  lineas_sin_costo: number
  descuentos: number
  cantidad_descuentos: number
  propinas: number
  fiado_del_dia: number
  abonos_del_dia: number
  te_deben: number
}

export interface Novedad {
  /** El número de la venta, o el de la corrección. */
  id: number
  hora: string
  quien: string
  monto: number
  motivo: string | null
  con_codigo: boolean
  /** Solo en las correcciones: qué se quitó y de qué mesa. */
  que: string | null
}

export interface NovedadesDia {
  fecha: string
  anulaciones: Novedad[]
  descuentos: Novedad[]
  correcciones: Novedad[]
}

// ------------------------------------------------------------------ fiado

export interface ClienteFiado {
  id: number
  nombre: string
  telefono: string | null
  /** Hasta cuánto puede deber. null: sin límite. */
  cupo: number | null
  activo: boolean
  /** Lo que debe hoy. */
  saldo: number
}

export interface MovimientoFiado {
  tipo: 'fiado' | 'abono'
  id: number
  fecha: string
  monto: number
  detalle: string
  anulado: boolean
}

export interface CuentaFiado extends ClienteFiado {
  movimientos: MovimientoFiado[]
}

export interface Comparacion {
  fecha: string
  total: number
  fecha_comparada: string
  total_comparado: number
  variacion_porcentaje: number | null
}

export interface ItemCobro {
  producto_id?: number
  plato_id?: number
  cantidad: number
}
