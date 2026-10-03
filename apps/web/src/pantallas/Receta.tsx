import { useEffect, useState } from 'react'

import { api } from '../api/cliente'
import type { Producto, RecetaLeer } from '../api/tipos'
import { cantidad as formatoCantidad, plata } from '../formato'

interface Linea {
  producto_id: number
  cantidad: string
}

export default function Receta({
  platoId,
  insumos,
  alGuardar,
}: {
  platoId: number
  insumos: Producto[]
  alGuardar: () => void
}) {
  const [receta, setReceta] = useState<RecetaLeer | null>(null)
  const [lineas, setLineas] = useState<Linea[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    api
      .get<RecetaLeer>(`/platos/${platoId}/receta`)
      .then((r) => {
        setReceta(r)
        setLineas(
          r.insumos.map((i) => ({ producto_id: i.producto_id, cantidad: String(i.cantidad) })),
        )
      })
      .catch((fallo) =>
        setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar la receta.'),
      )
  }, [platoId])

  const disponibles = insumos.filter(
    (p) => !lineas.some((l) => l.producto_id === p.id),
  )

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const guardada = await api.put<RecetaLeer>(
        `/platos/${platoId}/receta`,
        lineas
          .filter((l) => Number(l.cantidad.replace(',', '.')) > 0)
          .map((l) => ({
            producto_id: l.producto_id,
            cantidad: Number(l.cantidad.replace(',', '.')),
          })),
      )
      setReceta(guardada)
      alGuardar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar la receta.')
    } finally {
      setGuardando(false)
    }
  }

  if (!receta) return <p className="pista">{error ?? 'Cargando la receta…'}</p>

  const nombreDe = (id: number) => insumos.find((p) => p.id === id)?.nombre ?? `#${id}`
  const unidadDe = (id: number) =>
    insumos.find((p) => p.id === id)?.tipo_venta === 'peso' ? 'kg' : 'und'

  return (
    <div className="receta">
      <p className="pista">
        Lo que lleva un plato. Desde que tiene receta, venderlo descuenta estos insumos
        del inventario y su costo se calcula solo.
      </p>

      {error && <p className="aviso aviso-error">{error}</p>}

      {lineas.length === 0 && <p className="pista">Todavía no tiene receta.</p>}

      {lineas.map((linea, i) => (
        <div key={linea.producto_id} className="receta-linea">
          <span className="receta-nombre">{nombreDe(linea.producto_id)}</span>
          <input
            className="num"
            inputMode="decimal"
            value={linea.cantidad}
            onFocus={(e) => e.target.select()}
            onChange={(e) =>
              setLineas((todas) =>
                todas.map((l, j) => (i === j ? { ...l, cantidad: e.target.value } : l)),
              )
            }
          />
          <span className="receta-unidad">{unidadDe(linea.producto_id)}</span>
          <button
            className="btn-peligro"
            onClick={() => setLineas((todas) => todas.filter((_, j) => j !== i))}
          >
            Quitar
          </button>
        </div>
      ))}

      {disponibles.length > 0 && (
        <select
          className="receta-agregar"
          value=""
          onChange={(e) => {
            const id = Number(e.target.value)
            if (id) setLineas((todas) => [...todas, { producto_id: id, cantidad: '1' }])
          }}
        >
          <option value="">+ Agregar un insumo…</option>
          {disponibles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre}
            </option>
          ))}
        </select>
      )}

      <div className="receta-resumen">
        {receta.costo === null ? (
          <span className="sin-dato">
            {receta.insumos.length === 0
              ? 'Arma la receta o escríbele un costo a mano para saber cuánto deja.'
              : 'Falta el costo de algún insumo, así que todavía no se sabe cuánto deja.'}
          </span>
        ) : (
          <>
            <span>
              Cuesta <b className="num">{plata(receta.costo)}</b>
            </span>
            <span>
              Deja{' '}
              <b className={`num ${(receta.utilidad ?? 0) >= 0 ? 'deja-bien' : 'deja-mal'}`}>
                {plata(receta.utilidad ?? 0)}
              </b>
            </span>
          </>
        )}
      </div>

      {receta.insumos.length > 0 && (
        <div className="receta-detalle">
          {receta.insumos.map((i) => (
            <span key={i.producto_id}>
              {formatoCantidad(i.cantidad)} {unidadDe(i.producto_id)} de {i.nombre}
              {i.costo_total !== null && ` · ${plata(i.costo_total)}`}
            </span>
          ))}
        </div>
      )}

      <button className="btn-secundario" onClick={() => void guardar()} disabled={guardando}>
        {guardando ? 'Guardando…' : 'Guardar la receta'}
      </button>
    </div>
  )
}
