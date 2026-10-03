export type Rol = 'administrador' | 'vendedor' | 'mesero' | 'cocina'
export type EstadoCocina = 'pendiente' | 'listo'
export type MetodoPago = 'efectivo' | 'nequi' | 'daviplata' | 'tarjeta'
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

export interface Venta {
  id: number
  fecha_hora: string
  tipo: TipoCobro
  mesa: number | null
  total: number
  metodo_pago: MetodoPago
  vendedor_id: number
  anulada: boolean
  motivo_anulacion: string | null
  detalles: DetalleVenta[]
}

export interface DetallePedido extends DetalleVenta {
  notas: string | null
  estado_cocina: EstadoCocina
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
