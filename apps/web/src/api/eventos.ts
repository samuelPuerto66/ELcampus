import { useEffect, useRef, useState } from 'react'

import { leerSesion } from './cliente'

export interface Aviso {
  evento:
    | 'cuenta_pedida'
    | 'mesa_actualizada'
    | 'mesa_abierta'
    | 'mesa_cobrada'
    | 'plato_listo'
    | 'cocina_actualizada'
  datos: {
    pedido_id?: number
    mesa: number
    estado?: string
    total?: number
    items?: number
    nombre?: string
    detalle_id?: number
  }
}

/**
 * Canal en vivo con el servidor. Se reconecta solo: si se cae el WiFi del
 * local, la caja vuelve a engancharse sin que nadie toque nada.
 */
export function useEventos(alRecibir: (aviso: Aviso) => void) {
  const [conectado, setConectado] = useState(false)
  const manejador = useRef(alRecibir)
  manejador.current = alRecibir

  useEffect(() => {
    const sesion = leerSesion()
    if (!sesion) return

    let socket: WebSocket | null = null
    let reintento: number | undefined
    let vivo = true

    const conectar = () => {
      if (!vivo) return
      const protocolo = location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(
        `${protocolo}://${location.host}/api/eventos?token=${sesion.access_token}`,
      )

      socket.onopen = () => setConectado(true)
      socket.onmessage = (e) => {
        try {
          manejador.current(JSON.parse(e.data) as Aviso)
        } catch {
          /* un mensaje roto no debe tumbar la caja */
        }
      }
      socket.onclose = () => {
        setConectado(false)
        if (vivo) reintento = window.setTimeout(conectar, 3000)
      }
      socket.onerror = () => socket?.close()
    }

    conectar()

    return () => {
      vivo = false
      window.clearTimeout(reintento)
      socket?.close()
    }
  }, [])

  return conectado
}
