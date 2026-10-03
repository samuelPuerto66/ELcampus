import { useCallback, useEffect, useState } from 'react'

import { api } from '../api/cliente'
import { useEventos } from '../api/eventos'
import type { ItemComanda } from '../api/tipos'
import { cantidad as formatoCantidad } from '../formato'
import { useSesion } from '../sesion'

/** Minutos que lleva esperando un plato. */
function esperando(desde: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(desde).getTime()) / 60000))
}

/** La urgencia se ve de lejos: tranquilo, apurado, tarde. */
function urgencia(minutos: number): string {
  if (minutos >= 20) return 'tarde'
  if (minutos >= 10) return 'apurado'
  return ''
}

export default function Cocina() {
  const { sesion, salir } = useSesion()
  const [items, setItems] = useState<ItemComanda[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [, setReloj] = useState(0)

  const cargar = useCallback(async () => {
    try {
      setItems(await api.get<ItemComanda[]>('/cocina/pendientes'))
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar la comanda.')
    }
  }, [])

  const conectado = useEventos(() => void cargar())

  useEffect(() => {
    void cargar()
    // Red de seguridad por si el WebSocket se cayó sin avisar, y además
    // mantiene vivo el contador de minutos de espera.
    const latido = window.setInterval(() => {
      setReloj((n) => n + 1)
      void cargar()
    }, 20000)
    return () => window.clearInterval(latido)
  }, [cargar])

  async function marcarListo(item: ItemComanda) {
    // Se quita de la pantalla de una, sin esperar al servidor: en una
    // cocina ocupada, un botón que no responde se vuelve a presionar.
    setItems((actuales) => actuales?.filter((i) => i.id !== item.id) ?? null)
    try {
      await api.post(`/cocina/items/${item.id}/listo`)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo marcar.')
      void cargar()
    }
  }

  if (!items) return <p className="cargando">{error ?? 'Cargando la comanda…'}</p>

  const mesas = [...new Set(items.map((i) => i.mesa))].sort((a, b) => a - b)

  return (
    <div className="cocina">
      <header className="barra">
        <span className="marca">COCINA</span>
        <span>{items.length === 0 ? 'Todo al día' : `${items.length} por preparar`}</span>
        <span className="der">
          <span className={conectado ? 'chip-ok' : 'chip-mal'}>
            ● {conectado ? 'En línea' : 'Sin señal'}
          </span>
          <span className="pista">{sesion?.nombre}</span>
          <button className="btn-peligro" onClick={salir}>
            Salir
          </button>
        </span>
      </header>

      {error && <p className="aviso aviso-error">{error}</p>}

      {items.length === 0 ? (
        <div className="cocina-vacia">
          <span className="cocina-vacia-icono">🔥</span>
          <p>No hay nada pendiente. Los pedidos nuevos aparecen solos.</p>
        </div>
      ) : (
        <div className="cocina-mesas">
          {mesas.map((mesa) => {
            const deLaMesa = items.filter((i) => i.mesa === mesa)
            const masViejo = Math.max(...deLaMesa.map((i) => esperando(i.creado_en)))

            return (
              <section key={mesa} className={`comanda ${urgencia(masViejo)}`}>
                <header className="comanda-cabeza">
                  <span className="comanda-mesa">Mesa {mesa}</span>
                  <span className="comanda-espera">
                    {masViejo === 0 ? 'recién' : `hace ${masViejo} min`}
                  </span>
                </header>

                {deLaMesa.map((item) => (
                  <button
                    key={item.id}
                    className="comanda-item"
                    onClick={() => void marcarListo(item)}
                  >
                    <span className="comanda-cantidad">{formatoCantidad(item.cantidad)}</span>
                    <span className="comanda-nombre">
                      {item.nombre}
                      {item.notas && <small>{item.notas}</small>}
                    </span>
                    <span className="comanda-listo">Listo ✓</span>
                  </button>
                ))}
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
