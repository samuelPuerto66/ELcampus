export type Rol = 'administrador' | 'vendedor' | 'mesero'
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
}

export interface Plato {
  id: number
  nombre: string
  precio: number
  tipo: 'fijo' | 'especial'
  activo_desde: string | null
  activo_hasta: string | null
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

export interface ResumenDia {
  fecha: string
  total: number
  cantidad_ventas: number
  ticket_promedio: number
  mesas_atendidas: number
  por_metodo: { metodo_pago: MetodoPago; total: number; cantidad: number }[]
  mas_vendidos: { nombre: string; cantidad: number; total: number }[]
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
