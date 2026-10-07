import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useBandeja } from '../api/bandeja'
import { api, SinConexion } from '../api/cliente'
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
  const bandeja = useBandeja()
  const enEspera = bandeja.filter((e) => !e.rechazo)
  const rechazados = bandeja.filter((e) => e.rechazo)

  const cargar = useCallback(async () => {
    try {
      setPedidos(await api.get<Pedido[]>('/pedidos'))
      setError(null)
    } catch (fallo) {
      // Sin señal ya lo dice el aviso de arriba; no hace falta repetirlo.
      if (!(fallo instanceof SinConexion)) {
        setError(fallo instanceof Error ? fallo.message : 'No se pudieron cargar las mesas.')
      }
    }
  }, [])

  const conectado = useEventos(() => void cargar())

  // Al entrar, y cada vez que algo de la bandeja llega a la caja.
  useEffect(() => {
    void cargar()
  }, [enEspera.length, cargar])

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
        {enEspera.length > 0 && (
          <p className="aviso aviso-atencion">
            {enEspera.length === 1
              ? 'Hay 1 pedido guardado en este celular esperando señal.'
              : `Hay ${enEspera.length} pedidos guardados en este celular esperando señal.`}{' '}
            Se envían solos cuando vuelva el WiFi.
          </p>
        )}
        {rechazados.length > 0 && (
          <p className="aviso aviso-error">
            {rechazados.length === 1 ? 'Un pedido no entró' : `${rechazados.length} pedidos no entraron`}{' '}
            a la caja. Abre la mesa marcada con ✕ para revisarlo.
          </p>
        )}

        <div className="mesas">
          {Array.from({ length: MESAS_DEL_LOCAL }, (_, i) => i + 1).map((numero) => {
            const pedido = pedidos.find((p) => p.mesa === numero)
            const esperando = enEspera.some((e) => e.mesa === numero)
            const rechazo = rechazados.some((e) => e.mesa === numero)
            const estado =
              pedido?.estado === 'cuenta_pedida'
                ? 'cuenta'
                : pedido || esperando
                  ? 'ocupada'
                  : ''

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
                {(esperando || rechazo) && (
                  <span
                    className={`mesa-bandeja ${rechazo ? 'mal' : ''}`}
                    title={rechazo ? 'Un pedido no entró' : 'Esperando señal'}
                  >
                    {rechazo ? '✕' : '⏳'}
                  </span>
                )}
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
