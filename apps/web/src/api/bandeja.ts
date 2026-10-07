import { useSyncExternalStore } from 'react'

import { api, ErrorApi, leerSesion, SinConexion } from './cliente'
import type { Pedido } from './tipos'

/**
 * Bandeja de salida del mesero.
 *
 * Cuando el mesero confirma un pedido, primero queda guardado en el
 * celular y después se intenta subir. Si no hay señal, se queda en la
 * bandeja y se reintenta solo hasta que entra — el mesero sigue atendiendo
 * mientras tanto. Cada pedido lleva una clave propia: si la señal se cae
 * justo después de que el servidor lo recibió, el reintento no lo duplica.
 */

export interface LineaEnvio {
  producto_id?: number
  plato_id?: number
  nombre: string
  precio: number
  cantidad: number
  /** Para la cocina: "sin cebolla". */
  notas?: string
}

export interface Envio {
  clave: string
  mesa: number
  lineas: LineaEnvio[]
  creado: string
  /** Si el servidor lo rechazó (no por falta de señal), por qué. Un pedido
   *  rechazado no se reintenta solo: reintentarlo daría el mismo "no". */
  rechazo?: string
}

export type ResultadoEnvio =
  | { estado: 'enviado'; pedido: Pedido }
  | { estado: 'en_cola' }
  | { estado: 'rechazado'; motivo: string }

const LLAVE = 'elcampus.bandeja'
const CADA_CUANTO_REINTENTAR_MS = 5000

function leer(): Envio[] {
  try {
    const guardado = localStorage.getItem(LLAVE)
    return guardado ? (JSON.parse(guardado) as Envio[]) : []
  } catch {
    return []
  }
}

let envios: Envio[] = leer()
const oyentes = new Set<() => void>()

function cambiar(nuevos: Envio[]) {
  envios = nuevos
  try {
    if (nuevos.length === 0) localStorage.removeItem(LLAVE)
    else localStorage.setItem(LLAVE, JSON.stringify(nuevos))
  } catch {
    // Sin espacio o en modo privado: la bandeja sigue viva en memoria.
  }
  for (const oyente of oyentes) oyente()
}

function suscribir(oyente: () => void) {
  oyentes.add(oyente)
  return () => {
    oyentes.delete(oyente)
  }
}

/** Lo que hay en la bandeja, y la pantalla se actualiza sola cuando cambia. */
export function useBandeja(): Envio[] {
  return useSyncExternalStore(suscribir, () => envios)
}

/** Una clave al azar para el envío. `crypto.randomUUID` no existe cuando la
 *  app se abre por la IP del PC (http, no https), así que se arma a mano. */
export function nuevaClave(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

const recibidos = new Map<string, Pedido>()
let enCurso: Promise<void> | null = null

/** Sube lo que esté pendiente, en el orden en que se anotó. */
export function procesarBandeja(): Promise<void> {
  if (enCurso) return enCurso

  enCurso = (async () => {
    try {
      for (const envio of envios) {
        if (envio.rechazo) continue
        if (!leerSesion()) return

        try {
          const pedido = await api.post<Pedido>('/pedidos/enviar', {
            mesa: envio.mesa,
            clave: envio.clave,
            items: envio.lineas.map((l) => ({
              producto_id: l.producto_id ?? null,
              plato_id: l.plato_id ?? null,
              cantidad: l.cantidad,
              notas: l.notas ?? null,
            })),
          })
          recibidos.set(envio.clave, pedido)
          cambiar(envios.filter((e) => e.clave !== envio.clave))
        } catch (fallo) {
          // Sin señal, sesión vencida o el servidor con un problema
          // pasajero: se deja quieto y se reintenta más tarde.
          const pasajero =
            fallo instanceof SinConexion ||
            (fallo instanceof ErrorApi && (fallo.estado === 401 || fallo.estado >= 500))
          if (pasajero) return

          // El servidor dijo que no (un plato que ya no existe, por ejemplo).
          const motivo = fallo instanceof Error ? fallo.message : 'El servidor no lo aceptó.'
          cambiar(envios.map((e) => (e.clave === envio.clave ? { ...e, rechazo: motivo } : e)))
        }
      }
    } finally {
      enCurso = null
    }
  })()

  return enCurso
}

/** Guarda el pedido en el celular y trata de subirlo de una vez. */
export async function enviarPedido(mesa: number, lineas: LineaEnvio[]): Promise<ResultadoEnvio> {
  const envio: Envio = { clave: nuevaClave(), mesa, lineas, creado: new Date().toISOString() }
  cambiar([...envios, envio])

  await procesarBandeja()
  // Si ya había otra subida corriendo, esta pudo quedar por fuera de esa
  // vuelta: una segunda pasada la alcanza.
  if (envios.some((e) => e.clave === envio.clave && !e.rechazo)) await procesarBandeja()

  const pedido = recibidos.get(envio.clave)
  if (pedido) {
    recibidos.delete(envio.clave)
    return { estado: 'enviado', pedido }
  }
  const quedo = envios.find((e) => e.clave === envio.clave)
  if (quedo?.rechazo) return { estado: 'rechazado', motivo: quedo.rechazo }
  return { estado: 'en_cola' }
}

/** Saca un pedido de la bandeja: para descartarlo o para volver a anotarlo. */
export function quitarDeLaBandeja(clave: string) {
  cambiar(envios.filter((e) => e.clave !== clave))
}

// Reintento automático: cada tanto mientras haya algo pendiente, y apenas
// el celular avise que volvió la red.
window.setInterval(() => {
  if (envios.some((e) => !e.rechazo)) void procesarBandeja()
}, CADA_CUANTO_REINTENTAR_MS)
window.addEventListener('online', () => void procesarBandeja())
