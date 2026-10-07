const pesos = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
})

/** $59.200 — el peso colombiano no maneja centavos en caja. */
export const plata = (valor: number) => pesos.format(Math.round(valor))

/** 0,4 kg se muestra con coma; 2 unidades sin decimales sobrantes. */
export const cantidad = (valor: number) =>
  Number.isInteger(valor) ? String(valor) : valor.toFixed(3).replace(/\.?0+$/, '').replace('.', ',')

export const hora = (iso: string) =>
  new Date(iso).toLocaleTimeString('es-CO', { hour: 'numeric', minute: '2-digit' })

/**
 * Lee una cifra de plata como la escribe la gente en Colombia.
 *
 * "350.000" son trescientos cincuenta mil, no trescientos cincuenta: el
 * punto separa los miles. `Number("350.000")` da 350, y con eso un cierre
 * de caja reportaba un faltante de $349.650 que no existía. Aquí los puntos
 * y comas de miles se ignoran; solo una coma o un punto con uno o dos
 * dígitos al final se toma como centavos, y se redondea.
 *
 * Devuelve null si no hay ningún número escrito.
 */
export function leerPesos(texto: string): number | null {
  const limpio = texto.replace(/[\s$]/g, '')
  if (!limpio) return null

  const conCentavos = limpio.match(/^(.*)[.,](\d{1,2})$/)
  const entero = (conCentavos ? conCentavos[1] : limpio).replace(/\D/g, '')
  if (!entero && !conCentavos) return null

  const centavos = conCentavos ? Number(`0.${conCentavos[2]}`) : 0
  return Math.round(Number(entero || '0') + centavos)
}

/** Kilos o unidades: acá sí manda la coma decimal ("0,4" kg). */
export function leerCantidad(texto: string): number | null {
  const valor = Number(texto.trim().replace(',', '.'))
  return texto.trim() && Number.isFinite(valor) ? valor : null
}
