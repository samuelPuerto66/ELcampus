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
  /** Cómo se llama el precio de venta en el servidor. Lo que se vende por
   *  kilo lo guarda en `precio_por_kg`; mandarlo como `precio` le dañaría
   *  el precio al producto. */
  campoPrecio: 'precio' | 'precio_por_kg'
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
    campoPrecio: p.tipo_venta === 'peso' ? 'precio_por_kg' : 'precio',
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
    campoPrecio: 'precio',
    platoId: p.id,
  }
}

/** Lo que deja cada venta, en plata y en porcentaje. */
function margen(precio: number, costo: number | null) {
  if (costo === null || !precio) return null
  return { deja: precio - costo, porcentaje: Math.round(((precio - costo) / precio) * 100) }
}

/** Lo que la persona lleva escrito en una fila y todavía no ha guardado. */
interface Cambio {
  precio?: string
  costo?: string
}

export default function Catalogo() {
  const [filas, setFilas] = useState<Fila[] | null>(null)
  const [edicion, setEdicion] = useState<Record<string, Cambio>>({})
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
    const cambio = edicion[fila.clave] ?? {}
    const cambios: Record<string, number | null> = {}

    // "2.300" son dos mil trescientos, no 2,3.
    if (cambio.precio !== undefined) {
      const precio = leerPesos(cambio.precio)
      if (precio === null || precio <= 0) {
        setError(`El precio de venta de ${fila.nombre} tiene que ser un número mayor que cero.`)
        return
      }
      cambios[fila.campoPrecio] = precio
    }

    if (cambio.costo !== undefined) {
      // El costo sí se puede dejar en blanco: es "todavía no lo sé".
      const vacio = cambio.costo.trim() === ''
      const costo = vacio ? null : leerPesos(cambio.costo)
      if (!vacio && (costo === null || costo < 0)) {
        setError(`El costo de ${fila.nombre} no es un número válido.`)
        return
      }
      cambios.costo = costo
    }

    if (Object.keys(cambios).length === 0) return

    setGuardando(fila.clave)
    setError(null)
    try {
      await api.patch(fila.ruta, cambios)
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

  /** Lo escrito si lo hay; si no, lo que está guardado. */
  function valorEnPantalla(fila: Fila, campo: keyof Cambio): string {
    const escrito = edicion[fila.clave]?.[campo]
    if (escrito !== undefined) return escrito
    const guardado = campo === 'precio' ? fila.precio : fila.costo
    return guardado === null ? '' : String(guardado)
  }

  function escribir(fila: Fila, campo: keyof Cambio, valor: string) {
    setEdicion((actual) => ({
      ...actual,
      [fila.clave]: { ...actual[fila.clave], [campo]: valor },
    }))
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

          // La ganancia se calcula con lo que lleva escrito, no con lo
          // guardado: así se ve en el momento si el precio que está pensando
          // poner deja algo o no, antes de guardarlo.
          const precioEnPantalla = leerPesos(valorEnPantalla(fila, 'precio'))
          const costoTexto = valorEnPantalla(fila, 'costo')
          const costoEnPantalla = costoTexto.trim() === '' ? null : leerPesos(costoTexto)
          const m = margen(precioEnPantalla ?? 0, costoEnPantalla)

          return (
            <div key={fila.clave} className="fila-costo">
              <span className="fila-costo-nombre">
                {fila.nombre}
                <small>{fila.detalle}</small>
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
                <label className="campo-mini">
                  <small>Se vende a</small>
                  <input
                    className="num"
                    inputMode="numeric"
                    placeholder="venta"
                    value={valorEnPantalla(fila, 'precio')}
                    // Al entrar se selecciona lo que ya hay: escribir
                    // reemplaza el valor viejo en vez de pegarse a él.
                    onFocus={(e) => e.target.select()}
                    onChange={(e) => escribir(fila, 'precio', e.target.value)}
                  />
                </label>

                <label className="campo-mini">
                  <small>Me cuesta</small>
                  <input
                    className="num"
                    inputMode="numeric"
                    placeholder="costo"
                    value={valorEnPantalla(fila, 'costo')}
                    onFocus={(e) => e.target.select()}
                    onChange={(e) => escribir(fila, 'costo', e.target.value)}
                  />
                </label>

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
