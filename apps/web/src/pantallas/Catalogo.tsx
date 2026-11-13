import { useEffect, useRef, useState } from 'react'

import { api } from '../api/cliente'
import type { Producto } from '../api/tipos'
import { cantidad as formatoCantidad, leerPesos, milesAlEscribir, plata } from '../formato'

/**
 * Lo que se vende en la tienda: bebidas, cerveza, mecato.
 *
 * El restaurante va aparte, en la pestaña Menú: solo abre los fines de
 * semana y se maneja con platos y recetas, no con códigos de barras. Los
 * insumos de cocina tampoco salen aquí por lo mismo.
 */

const SIN_SECCION = 'Sin sección'

/** Para agrupar sin que «BEBIDA» y «bebidas» queden en secciones distintas. */
const llaveDeSeccion = (texto: string) =>
  texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim()
    .toLowerCase()

/** Sin tildes y en minúscula: buscar "gaseosa" encuentra "Gaseosa Postobón". */
const simple = (texto: string) =>
  texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()

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

/**
 * Desplegable propio, con los colores de la casa.
 *
 * El `<select>` del navegador dibuja su lista abierta el sistema operativo,
 * no la página: queda con el azul de Windows y no hay CSS que lo alcance.
 * Por eso va uno hecho a mano.
 */
function Secciones({
  valor,
  opciones,
  alElegir,
}: {
  valor: string
  opciones: { llave: string; texto: string; cuantos: number }[]
  alElegir: (llave: string) => void
}) {
  const [abierto, setAbierto] = useState(false)
  const caja = useRef<HTMLDivElement>(null)

  // Se cierra al tocar por fuera o con Esc, como cualquier desplegable.
  useEffect(() => {
    if (!abierto) return
    const afuera = (e: MouseEvent) => {
      if (!caja.current?.contains(e.target as Node)) setAbierto(false)
    }
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAbierto(false)
    }
    document.addEventListener('mousedown', afuera)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', afuera)
      document.removeEventListener('keydown', escape)
    }
  }, [abierto])

  const elegida = opciones.find((o) => o.llave === valor) ?? opciones[0]

  return (
    <div className="desplegable" ref={caja}>
      <button
        type="button"
        className={`desplegable-boton ${abierto ? 'abierto' : ''}`}
        onClick={() => setAbierto((a) => !a)}
        aria-expanded={abierto}
        aria-haspopup="listbox"
      >
        <span>
          {elegida.texto} <span className="desplegable-cuantos">{elegida.cuantos}</span>
        </span>
        <span className="desplegable-flecha" aria-hidden="true">
          ▾
        </span>
      </button>

      {abierto && (
        <ul className="desplegable-lista" role="listbox">
          {opciones.map((o) => (
            <li key={o.llave}>
              <button
                type="button"
                role="option"
                aria-selected={o.llave === valor}
                className={`desplegable-opcion ${o.llave === valor ? 'elegida' : ''}`}
                onClick={() => {
                  alElegir(o.llave)
                  setAbierto(false)
                }}
              >
                <span>{o.texto}</span>
                <span className="desplegable-cuantos">{o.cuantos}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function Catalogo() {
  const [productos, setProductos] = useState<Producto[] | null>(null)
  const [edicion, setEdicion] = useState<Record<number, Cambio>>({})
  const [abierto, setAbierto] = useState<number | null>(null)
  const [guardando, setGuardando] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [listo, setListo] = useState<string | null>(null)
  const [busqueda, setBusqueda] = useState('')
  const [seccion, setSeccion] = useState('')

  async function cargar() {
    try {
      // Sin insumos a propósito: la carne y el pescado del restaurante no
      // son mercancía de tienda.
      setProductos(await api.get<Producto[]>('/productos'))
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar la tienda.')
    }
  }

  useEffect(() => {
    void cargar()
  }, [])

  useEffect(() => {
    if (!listo) return
    const reloj = setTimeout(() => setListo(null), 4000)
    return () => clearTimeout(reloj)
  }, [listo])

  const seccionDe = (p: Producto) => p.categoria?.trim() || SIN_SECCION
  const precioDe = (p: Producto) => p.precio_de_venta

  function escribir(p: Producto, campo: keyof Cambio, valor: string) {
    setEdicion((actual) => ({ ...actual, [p.id]: { ...actual[p.id], [campo]: valor } }))
  }

  /** Lo escrito si lo hay; si no, lo que está guardado. */
  function enPantalla(p: Producto, campo: keyof Cambio): string {
    const escrito = edicion[p.id]?.[campo]
    if (escrito !== undefined) return escrito
    if (campo === 'nombre') return p.nombre
    if (campo === 'categoria') return p.categoria ?? ''
    if (campo === 'precio') return String(precioDe(p))
    return p.costo === null ? '' : String(p.costo)
  }

  function cerrar(id: number) {
    setAbierto(null)
    setEdicion((actual) => {
      const { [id]: _, ...resto } = actual
      return resto
    })
  }

  async function guardar(p: Producto) {
    const cambio = edicion[p.id] ?? {}
    const cambios: Record<string, string | number | null> = {}

    if (cambio.nombre !== undefined) {
      const nombre = cambio.nombre.trim()
      if (!nombre) {
        setError('El nombre no puede quedar vacío.')
        return
      }
      cambios.nombre = nombre
    }

    if (cambio.categoria !== undefined) cambios.categoria = cambio.categoria.trim() || null

    // "2.300" son dos mil trescientos, no 2,3.
    if (cambio.precio !== undefined) {
      const precio = leerPesos(cambio.precio)
      if (precio === null || precio <= 0) {
        setError(`El precio de venta de ${p.nombre} tiene que ser mayor que cero.`)
        return
      }
      // Lo que se vende por kilo guarda su precio en otro campo; mandarlo
      // como `precio` le dañaría el precio al producto.
      cambios[p.tipo_venta === 'peso' ? 'precio_por_kg' : 'precio'] = precio
    }

    if (cambio.costo !== undefined) {
      // El costo sí se puede dejar en blanco: es "todavía no lo sé".
      const vacio = cambio.costo.trim() === ''
      const costo = vacio ? null : leerPesos(cambio.costo)
      if (!vacio && (costo === null || costo < 0)) {
        setError(`El costo de ${p.nombre} no es un número válido.`)
        return
      }
      cambios.costo = costo
    }

    if (Object.keys(cambios).length === 0) {
      cerrar(p.id)
      return
    }

    setGuardando(p.id)
    setError(null)
    try {
      await api.patch(`/productos/${p.id}`, cambios)
      cerrar(p.id)
      setListo(`${cambios.nombre ?? p.nombre} quedó guardado.`)
      await cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar.')
    } finally {
      setGuardando(null)
    }
  }

  if (error && !productos) return <p className="aviso aviso-error">{error}</p>
  if (!productos) return <p className="cargando">Cargando la tienda…</p>

  // Las secciones salen de lo que haya cargado, no de una lista fija: el
  // negocio inventa las suyas. Se juntan sin mirar mayúsculas ni tildes
  // para que «BEBIDA» y «bebidas» no queden como dos secciones.
  const porLlave = new Map<string, { texto: string; items: Producto[] }>()
  for (const p of productos) {
    const texto = seccionDe(p)
    const llave = llaveDeSeccion(texto)
    const grupo = porLlave.get(llave)
    if (grupo) grupo.items.push(p)
    else porLlave.set(llave, { texto, items: [p] })
  }
  const secciones = [...porLlave.entries()].sort((a, b) =>
    a[1].texto.localeCompare(b[1].texto, 'es'),
  )

  const buscado = simple(busqueda.trim())
  const coincide = (p: Producto) =>
    (!seccion || llaveDeSeccion(seccionDe(p)) === seccion) &&
    (!buscado ||
      simple(p.nombre).includes(buscado) ||
      p.codigo_barras.includes(busqueda.trim()))

  const grupos = secciones
    .map(([llave, { texto, items }]) => ({
      llave,
      texto,
      items: items
        .filter(coincide)
        .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
    }))
    .filter((g) => g.items.length > 0)

  const cuantosSalen = grupos.reduce((suma, g) => suma + g.items.length, 0)
  const sinCosto = productos.filter((p) => p.costo === null).length

  const opciones = [
    { llave: '', texto: 'Todas las secciones', cuantos: productos.length },
    ...secciones.map(([llave, { texto, items }]) => ({
      llave,
      texto,
      cuantos: items.length,
    })),
  ]

  return (
    <section className="tarjeta">
      <div className="catalogo">
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
          <label className="campo-mini catalogo-seccion">
            <small>Sección</small>
            <Secciones valor={seccion} opciones={opciones} alElegir={setSeccion} />
          </label>
        </div>

        {sinCosto > 0 && (
          <p className="pista">
            {sinCosto === 1
              ? 'A 1 producto le falta el costo: sin él no se sabe cuánto deja.'
              : `A ${sinCosto} productos les falta el costo: sin él no se sabe cuánto dejan.`}
          </p>
        )}

        {error && <p className="aviso aviso-error">{error}</p>}
        {listo && <p className="aviso aviso-ok">{listo}</p>}

        {cuantosSalen === 0 && (
          <p className="pista">No hay nada que coincida con lo que buscaste.</p>
        )}

        {grupos.map((grupo) => (
          <div key={grupo.llave} className="catalogo-grupo">
            <h3 className="catalogo-grupo-titulo">
              {grupo.texto}
              <span className="conteo">{grupo.items.length}</span>
            </h3>

            {grupo.items.map((p) => {
              const editando = abierto === p.id
              // La ganancia se calcula con lo que lleva escrito: así se ve en
              // el momento si el precio que está pensando poner deja algo.
              const precio = editando ? leerPesos(enPantalla(p, 'precio')) : precioDe(p)
              const textoCosto = enPantalla(p, 'costo')
              const costo =
                editando && textoCosto.trim() === '' ? null : editando ? leerPesos(textoCosto) : p.costo
              const m = margen(precio ?? 0, costo)

              return (
                <div key={p.id} className={`articulo ${editando ? 'abierto' : ''}`}>
                  <button
                    type="button"
                    className="articulo-fila"
                    onClick={() => (editando ? cerrar(p.id) : setAbierto(p.id))}
                    aria-expanded={editando}
                  >
                    <span className="articulo-quien">
                      <b>{p.nombre}</b>
                      <small>
                        <span className={p.stock_actual <= p.alerta_minima ? 'quedan-pocos' : ''}>
                          quedan {formatoCantidad(p.stock_actual)}
                          {p.tipo_venta === 'peso' ? ' kg' : ''}
                        </span>
                        {p.codigo_barras && (
                          <>
                            <span className="articulo-separador">·</span>
                            <span className="articulo-codigo num">{p.codigo_barras}</span>
                          </>
                        )}
                      </small>
                    </span>

                    <span className="articulo-precio num">
                      {plata(precioDe(p))}
                      {p.tipo_venta === 'peso' && <small> /kg</small>}
                    </span>

                    <span className="articulo-margen">
                      {m ? (
                        <>
                          <b className={m.deja >= 0 ? 'deja-bien' : 'deja-mal'}>
                            {plata(m.deja)}
                          </b>
                          <small>{m.porcentaje}%</small>
                        </>
                      ) : (
                        <small className="sin-dato">sin costo</small>
                      )}
                    </span>

                    <span className="articulo-flecha" aria-hidden="true">
                      {editando ? '▴' : '▾'}
                    </span>
                  </button>

                  {editando && (
                    <div className="articulo-editor">
                      <label className="campo-mini campo-nombre">
                        <small>Nombre</small>
                        <input
                          value={enPantalla(p, 'nombre')}
                          onFocus={(e) => e.target.select()}
                          onChange={(e) => escribir(p, 'nombre', e.target.value)}
                          autoComplete="off"
                        />
                      </label>

                      <label className="campo-mini">
                        <small>Se vende a</small>
                        <input
                          className="num"
                          inputMode="numeric"
                          value={milesAlEscribir(enPantalla(p, 'precio'))}
                          onFocus={(e) => e.target.select()}
                          onChange={(e) => escribir(p, 'precio', milesAlEscribir(e.target.value))}
                        />
                      </label>

                      <label className="campo-mini">
                        <small>Me cuesta</small>
                        <input
                          className="num"
                          inputMode="numeric"
                          value={milesAlEscribir(enPantalla(p, 'costo'))}
                          placeholder="—"
                          onFocus={(e) => e.target.select()}
                          onChange={(e) => escribir(p, 'costo', milesAlEscribir(e.target.value))}
                        />
                      </label>

                      <label className="campo-mini">
                        <small>Sección</small>
                        <input
                          list="secciones-tienda"
                          value={enPantalla(p, 'categoria')}
                          onFocus={(e) => e.target.select()}
                          onChange={(e) => escribir(p, 'categoria', e.target.value)}
                          autoComplete="off"
                        />
                      </label>

                      <div className="articulo-botones">
                        <button
                          type="button"
                          className="btn-secundario btn-angosto"
                          onClick={() => void guardar(p)}
                          disabled={guardando === p.id}
                        >
                          {guardando === p.id ? 'Guardando…' : 'Guardar'}
                        </button>
                        <button
                          type="button"
                          className="btn-secundario btn-angosto"
                          onClick={() => cerrar(p.id)}
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}

        {/* Sugerencias al escribir la sección: así se reusan las que ya
            existen en vez de inventar «BEBIDA» cuando ya había «Bebidas». */}
        <datalist id="secciones-tienda">
          {secciones
            .filter(([, g]) => g.texto !== SIN_SECCION)
            .map(([llave, g]) => (
              <option key={llave} value={g.texto} />
            ))}
        </datalist>
      </div>
    </section>
  )
}
