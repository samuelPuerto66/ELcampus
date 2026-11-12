import { useEffect, useState } from 'react'

import { api } from '../api/cliente'
import type { Plato, Producto } from '../api/tipos'
import { cantidad as formatoCantidad, leerPesos, plata } from '../formato'
import Receta from './Receta'

/** Platos y productos se muestran juntos, así que cada cosa se vuelve una
 *  fila con los mismos datos. Los platos no tienen existencias ni código. */
interface Fila {
  clave: string
  ruta: string
  nombre: string
  detalle: string
  precio: number
  costo: number | null
  /** Para agrupar y para el desplegable. */
  categoria: string
  /** Cuántos quedan. null en los platos: no se cuentan. */
  stock: number | null
  /** Para buscar escaneando. Los platos no tienen. */
  codigo: string
  porKilo: boolean
  /** Cómo se llama el precio de venta en el servidor. Lo que se vende por
   *  kilo lo guarda en `precio_por_kg`; mandarlo como `precio` le dañaría
   *  el precio al producto. */
  campoPrecio: 'precio' | 'precio_por_kg'
  platoId?: number
  esInsumo?: boolean
}

const PLATOS = 'Platos del restaurante'
const SIN_CATEGORIA = 'Sin categoría'

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
    categoria: p.es_insumo
      ? 'Insumos de cocina'
      : (p.categoria?.trim() || SIN_CATEGORIA),
    stock: p.stock_actual,
    codigo: p.codigo_barras ?? '',
    porKilo: p.tipo_venta === 'peso',
    campoPrecio: p.tipo_venta === 'peso' ? 'precio_por_kg' : 'precio',
    esInsumo: p.es_insumo,
  }
}

function dePlato(p: Plato): Fila {
  return {
    clave: `plato-${p.id}`,
    ruta: `/platos/${p.id}`,
    nombre: p.nombre,
    detalle: p.tipo === 'especial' ? 'plato que rota' : 'plato fijo',
    precio: p.precio,
    costo: p.costo_efectivo ?? p.costo,
    categoria: PLATOS,
    stock: null,
    codigo: '',
    porKilo: false,
    campoPrecio: 'precio',
    platoId: p.id,
  }
}

/** Sin tildes y en minúscula: buscar "gaseosa" encuentra "Gaseosa Postobón". */
const simple = (texto: string) =>
  texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** Lo que deja cada venta, en plata y en porcentaje. */
function margen(precio: number, costo: number | null) {
  if (costo === null || !precio) return null
  return { deja: precio - costo, porcentaje: Math.round(((precio - costo) / precio) * 100) }
}

/** Lo que la persona lleva escrito en una fila y todavía no ha guardado. */
interface Cambio {
  nombre?: string
  categoria?: string
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
  const [busqueda, setBusqueda] = useState('')
  const [categoria, setCategoria] = useState('')

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
    const cambios: Record<string, string | number | null> = {}

    if (cambio.nombre !== undefined) {
      const nombre = cambio.nombre.trim()
      if (!nombre) {
        setError('El nombre no puede quedar vacío.')
        return
      }
      cambios.nombre = nombre
    }

    // La sección solo existe en los productos; los platos van todos juntos.
    if (cambio.categoria !== undefined && fila.platoId === undefined) {
      cambios.categoria = cambio.categoria.trim() || null
    }

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
    if (campo === 'nombre') return fila.nombre
    if (campo === 'categoria') return fila.categoria === SIN_CATEGORIA ? '' : fila.categoria
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

  // Las categorías salen de lo que haya cargado, no de una lista fija: el
  // negocio inventa las suyas al cargar los productos.
  const categorias = [...new Set(filas.map((f) => f.categoria))].sort((a, b) =>
    a.localeCompare(b, 'es'),
  )

  // Buscar por nombre o por código: escanear el producto con el cursor en la
  // casilla lo deja solo en pantalla, sin tener que leer la lista entera.
  const buscado = simple(busqueda.trim())
  const visibles = filas.filter(
    (f) =>
      (!categoria || f.categoria === categoria) &&
      (!buscado || simple(f.nombre).includes(buscado) || f.codigo.includes(busqueda.trim())),
  )

  // Agrupadas y ordenadas: así se revisa una sección completa de un vistazo.
  const grupos = categorias
    .map((cat) => ({ cat, filas: visibles.filter((f) => f.categoria === cat) }))
    .filter((g) => g.filas.length > 0)
  grupos.forEach((g) => g.filas.sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')))

  return (
    <section className="tarjeta">
      <div className="catalogo">
        <p className="pista">
          El costo es lo que te cuesta comprar o preparar cada cosa. Sin él, el sistema
          solo sabe cuánto vendiste, nunca cuánto ganaste.
        </p>

        {/* Sugerencias al escribir la sección: así se reusan las que ya
            existen en vez de inventar «BEBIDA» cuando ya había «bebidas». */}
        <datalist id="secciones-catalogo">
          {categorias
            .filter((c) => c !== PLATOS && c !== SIN_CATEGORIA)
            .map((c) => (
              <option key={c} value={c} />
            ))}
        </datalist>

        <div className="catalogo-filtros">
          <label className="campo-mini catalogo-buscar">
            <small>Buscar</small>
            <input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Escribe el nombre o escanea el código"
              autoComplete="off"
            />
          </label>
          <label className="campo-mini">
            <small>Sección</small>
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)}>
              <option value="">Todas ({filas.length})</option>
              {categorias.map((c) => (
                <option key={c} value={c}>
                  {c} ({filas.filter((f) => f.categoria === c).length})
                </option>
              ))}
            </select>
          </label>
          {(busqueda || categoria) && (
            <button
              type="button"
              className="btn-secundario btn-angosto"
              onClick={() => {
                setBusqueda('')
                setCategoria('')
              }}
            >
              Ver todo
            </button>
          )}
        </div>

        {visibles.length === 0 && (
          <p className="pista">
            No hay nada que coincida con lo que buscaste.
          </p>
        )}

        {sinCosto > 0 && (
          <p className="aviso aviso-atencion">
            Faltan {sinCosto} por cargar.
          </p>
        )}
        {error && <p className="aviso aviso-error">{error}</p>}

        {grupos.map((grupo) => (
          <div key={grupo.cat} className="catalogo-grupo">
            <h3 className="catalogo-grupo-titulo">
              {grupo.cat}
              <span className="conteo">{grupo.filas.length}</span>
            </h3>

        {grupo.filas.map((fila) => {
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
                <small>
                  {fila.detalle}
                  {fila.stock !== null && (
                    <>
                      {' · '}
                      <b className={fila.stock <= 5 ? 'quedan-pocos' : ''}>
                        quedan {formatoCantidad(fila.stock)}
                        {fila.porKilo ? ' kg' : ''}
                      </b>
                    </>
                  )}
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
                <label className="campo-mini campo-nombre">
                  <small>Nombre</small>
                  <input
                    value={valorEnPantalla(fila, 'nombre')}
                    onFocus={(e) => e.target.select()}
                    onChange={(e) => escribir(fila, 'nombre', e.target.value)}
                    autoComplete="off"
                  />
                </label>

                {fila.platoId === undefined && (
                  <label className="campo-mini">
                    <small>Sección</small>
                    <input
                      list="secciones-catalogo"
                      value={valorEnPantalla(fila, 'categoria')}
                      onFocus={(e) => e.target.select()}
                      onChange={(e) => escribir(fila, 'categoria', e.target.value)}
                      placeholder="bebidas"
                      autoComplete="off"
                    />
                  </label>
                )}

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
        ))}
      </div>
    </section>
  )
}
