import { useEffect, useState } from 'react'

import { api } from '../api/cliente'
import type { Plato, Producto } from '../api/tipos'
import { leerPesos, plata } from '../formato'
import Receta from './Receta'

interface Fila {
  clave: string
  ruta: string
  nombre: string
  detalle: string
  precio: number
  costo: number | null
  platoId?: number
  esInsumo?: boolean
}

function deProducto(p: Producto): Fila {
  return {
    clave: `producto-${p.id}`,
    ruta: `/productos/${p.id}`,
    nombre: p.nombre,
    detalle: p.es_insumo
      ? 'insumo de cocina'
      : p.tipo_venta === 'peso'
        ? 'por kilo'
        : (p.categoria ?? 'producto'),
    precio: p.precio_de_venta,
    costo: p.costo,
    esInsumo: p.es_insumo,
  }
}

function dePlato(p: Plato): Fila {
  return {
    clave: `plato-${p.id}`,
    ruta: `/platos/${p.id}`,
    nombre: p.nombre,
    detalle: p.tipo === 'especial' ? 'especial' : 'plato fijo',
    precio: p.precio,
    costo: p.costo_efectivo ?? p.costo,
    platoId: p.id,
  }
}

/** Lo que deja cada venta, en plata y en porcentaje. */
function margen(precio: number, costo: number | null) {
  if (costo === null || !precio) return null
  return { deja: precio - costo, porcentaje: Math.round(((precio - costo) / precio) * 100) }
}

export default function Catalogo() {
  const [filas, setFilas] = useState<Fila[] | null>(null)
  const [edicion, setEdicion] = useState<Record<string, string>>({})
  const [guardando, setGuardando] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [insumos, setInsumos] = useState<Producto[]>([])
  const [recetaAbierta, setRecetaAbierta] = useState<number | null>(null)

  async function cargar() {
    try {
      const [productos, platos] = await Promise.all([
        api.get<Producto[]>('/productos?incluir_insumos=true'),
        api.get<Plato[]>('/platos?solo_vigentes=false'),
      ])
      setFilas([...productos.map(deProducto), ...platos.map(dePlato)])
      setInsumos(productos.filter((p) => p.es_insumo))
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar el catálogo.')
    }
  }

  useEffect(() => {
    void cargar()
  }, [])

  async function guardar(fila: Fila) {
    const escrito = edicion[fila.clave]
    // "2.300" son dos mil trescientos, no 2,3.
    const costo = escrito.trim() === '' ? null : leerPesos(escrito)
    if (escrito.trim() !== '' && costo === null) {
      setError(`El costo de ${fila.nombre} no es un número válido.`)
      return
    }

    setGuardando(fila.clave)
    try {
      await api.patch(fila.ruta, { costo })
      setEdicion((actual) => {
        const { [fila.clave]: _, ...resto } = actual
        return resto
      })
      await cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar.')
    } finally {
      setGuardando(null)
    }
  }

  if (error && !filas) return <p className="aviso aviso-error">{error}</p>
  if (!filas) return <p className="cargando">Cargando el catálogo…</p>

  const sinCosto = filas.filter((f) => f.costo === null).length

  return (
    <section className="tarjeta">
      <div className="catalogo">
        <p className="pista">
          El costo es lo que te cuesta comprar o preparar cada cosa. Sin él, el sistema
          solo sabe cuánto vendiste, nunca cuánto ganaste.
        </p>

        {sinCosto > 0 && (
          <p className="aviso aviso-atencion">
            Faltan {sinCosto} por cargar.
          </p>
        )}
        {error && <p className="aviso aviso-error">{error}</p>}

        {filas.map((fila) => {
          const editando = edicion[fila.clave] !== undefined
          const m = margen(fila.precio, fila.costo)

          return (
            <div key={fila.clave} className="fila-costo">
              <span className="fila-costo-nombre">
                {fila.nombre}
                <small>
                  {fila.detalle} · se vende a {plata(fila.precio)}
                </small>
              </span>

              <span className="fila-costo-margen">
                {m ? (
                  <>
                    <b className={m.deja >= 0 ? 'deja-bien' : 'deja-mal'}>{plata(m.deja)}</b>
                    <small>{m.porcentaje}% de ganancia</small>
                  </>
                ) : (
                  <small className="sin-dato">sin costo</small>
                )}
              </span>

              <span className="fila-costo-editar">
                <input
                  className="num"
                  inputMode="numeric"
                  placeholder="costo"
                  value={editando ? edicion[fila.clave] : (fila.costo ?? '')}
                  // Al entrar se selecciona lo que ya hay: escribir reemplaza
                  // el costo viejo en vez de pegarse a él y multiplicarlo.
                  onFocus={(e) => e.target.select()}
                  onChange={(e) =>
                    setEdicion((actual) => ({ ...actual, [fila.clave]: e.target.value }))
                  }
                />
                {editando && (
                  <button
                    className="btn-secundario btn-angosto"
                    onClick={() => void guardar(fila)}
                    disabled={guardando === fila.clave}
                  >
                    {guardando === fila.clave ? '…' : 'Guardar'}
                  </button>
                )}
                {fila.platoId !== undefined && (
                  <button
                    className="btn-secundario btn-angosto"
                    onClick={() =>
                      setRecetaAbierta((abierto) =>
                        abierto === fila.platoId ? null : fila.platoId!,
                      )
                    }
                  >
                    {recetaAbierta === fila.platoId ? 'Cerrar receta' : 'Receta'}
                  </button>
                )}
              </span>

              {fila.platoId !== undefined && recetaAbierta === fila.platoId && (
                <div className="fila-costo-receta">
                  <Receta
                    platoId={fila.platoId}
                    insumos={insumos}
                    alGuardar={() => void cargar()}
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
