import { useEffect, useState } from 'react'

import { api } from '../api/cliente'
import type { Plato } from '../api/tipos'
import { plata } from '../formato'

/**
 * El menú de platos dentro de la caja, para vender para llevar.
 *
 * Los platos no tienen código de barras: sin esto, una picada para llevar
 * solo se podía vender abriendo una mesa de mentiras.
 */
export default function ElegirPlato({
  alElegir,
  cerrar,
}: {
  alElegir: (plato: Plato) => void
  cerrar: () => void
}) {
  const [platos, setPlatos] = useState<Plato[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Plato[]>('/platos')
      .then(setPlatos)
      .catch((fallo) =>
        setError(fallo instanceof Error ? fallo.message : 'No se pudieron cargar los platos.'),
      )
  }, [])

  return (
    <div className="platos-caja">
      <div className="opcion-cabeza">
        <span className="etiqueta">Platos para llevar · van a la cocina al cobrar</span>
        <button className="btn-peligro" onClick={cerrar}>
          Cerrar
        </button>
      </div>
      {error && <p className="aviso aviso-error">{error}</p>}
      {platos === null && !error && <p className="pista">Cargando el menú…</p>}
      <div className="platos-caja-lista">
        {platos?.map((plato) => (
          <button
            key={plato.id}
            className={`tarjeta-item ${plato.tipo === 'especial' ? 'especial' : ''}`}
            onClick={() => alElegir(plato)}
          >
            <b>{plato.nombre}</b>
            <small className="num">{plata(plato.precio)}</small>
          </button>
        ))}
      </div>
    </div>
  )
}
