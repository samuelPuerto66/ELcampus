import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/cliente'
import { useEventos } from '../api/eventos'
import type { Pedido } from '../api/tipos'
import { plata } from '../formato'
import { useSesion } from '../sesion'
import Fondo from './Fondo'

// Cuántas mesas tiene el local. Cuando el negocio ponga o quite mesas,
// se cambia este número.
const MESAS_DEL_LOCAL = 16

export default function Mesas() {
  const { sesion, salir } = useSesion()
  const [pedidos, setPedidos] = useState<Pedido[]>([])
  const [error, setError] = useState<string | null>(null)
  const navegar = useNavigate()

  const cargar = useCallback(async () => {
    try {
      setPedidos(await api.get<Pedido[]>('/pedidos'))
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudieron cargar las mesas.')
    }
  }, [])

  const conectado = useEventos(() => void cargar())

  useEffect(() => {
    void cargar()
  }, [cargar])

  // Tocar una mesa solo la abre en pantalla. La mesa se ocupa de verdad
  // cuando el mesero confirma el primer pedido, no antes.
  function tocarMesa(numero: number) {
    navegar(`/mesa/${numero}`)
  }

  return (
    <div className="celular-pantalla">
      <Fondo />
      <header className="barra">
        <span className="marca">MESAS</span>
        <span className="der">
          <span className={conectado ? 'chip-ok' : 'chip-mal'}>
            ● {conectado ? 'En línea' : 'Sin señal'}
          </span>
          <button className="btn-peligro" onClick={salir}>
            Salir
          </button>
        </span>
      </header>

      <div className="celular-cuerpo">
        {!conectado && (
          <p className="aviso aviso-atencion">
            Sin conexión con la caja. Revisa el WiFi del local — se reconecta solo.
          </p>
        )}
        {error && <p className="aviso aviso-error">{error}</p>}

        <div className="mesas">
          {Array.from({ length: MESAS_DEL_LOCAL }, (_, i) => i + 1).map((numero) => {
            const pedido = pedidos.find((p) => p.mesa === numero)
            const estado = pedido?.estado === 'cuenta_pedida' ? 'cuenta' : pedido ? 'ocupada' : ''

            return (
              <button
                key={numero}
                className={`mesa ${estado}`}
                onClick={() => tocarMesa(numero)}
              >
                <span className="mesa-numero">{numero}</span>
                <span className="mesa-estado">
                  {pedido?.estado === 'cuenta_pedida'
                    ? 'Cuenta'
                    : pedido
                      ? 'Ocupada'
                      : 'Libre'}
                </span>
                {pedido && <span className="mesa-total num">{plata(pedido.total)}</span>}
              </button>
            )
          })}
        </div>
      </div>

      <footer className="celular-pie">
        <span className="pista">
          {sesion?.nombre} · toca una mesa para tomar el pedido
        </span>
      </footer>
    </div>
  )
}
