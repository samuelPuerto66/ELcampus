import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'

import { api } from '../api/cliente'
import type { ConsultaCodigo, Producto } from '../api/tipos'
import { leerCantidad, leerPesos, plata } from '../formato'

interface Borrador {
  codigo_barras: string
  nombre: string
  precio: string
  costo: string
  stock: string
  categoria: string
  esInsumo: boolean
  sugerido: boolean
}

function vacio(codigo: string, nombre: string, sugerido: boolean): Borrador {
  return {
    codigo_barras: codigo,
    nombre,
    precio: '',
    costo: '',
    stock: '',
    categoria: '',
    esInsumo: false,
    sugerido,
  }
}

export default function CargarProductos() {
  const [codigo, setCodigo] = useState('')
  const [borrador, setBorrador] = useState<Borrador | null>(null)
  const [cargados, setCargados] = useState<Producto[]>([])
  const [aviso, setAviso] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const campoCodigo = useRef<HTMLInputElement>(null)
  const campoNombre = useRef<HTMLInputElement>(null)

  // Se carga en tandas largas: el cursor vuelve solo al escáner para poder
  // encadenar producto tras producto sin tocar el mouse.
  useEffect(() => {
    if (borrador) campoNombre.current?.focus()
    else campoCodigo.current?.focus()
  }, [borrador])

  async function escanear(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    const leido = codigo.trim()
    setCodigo('')
    if (!leido || ocupado) return

    setOcupado(true)
    setError(null)
    setAviso(null)
    try {
      const consulta = await api.get<ConsultaCodigo>(
        `/productos/consultar/${encodeURIComponent(leido)}`,
      )
      if (consulta.registrado) {
        setAviso(
          `${consulta.registrado.nombre} ya estaba registrado · ${plata(
            consulta.registrado.precio_de_venta,
          )}`,
        )
        return
      }
      setBorrador(vacio(leido, consulta.nombre_sugerido ?? '', !!consulta.nombre_sugerido))
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo consultar el código.')
    } finally {
      setOcupado(false)
    }
  }

  async function guardar(e: FormEvent) {
    e.preventDefault()
    if (!borrador || ocupado) return

    // "3.500" son tres mil quinientos. Leído como número de computador
    // daba 3,5 y la cerveza quedaba a cuatro pesos.
    const precio = leerPesos(borrador.precio)
    const costo = leerPesos(borrador.costo)
    const stock = leerCantidad(borrador.stock)
    if (!borrador.nombre.trim()) {
      setError('Ponle un nombre al producto.')
      return
    }
    if (!precio || precio <= 0) {
      setError('El precio tiene que ser mayor que cero.')
      return
    }
    if (borrador.stock.trim() && (stock === null || stock < 0)) {
      setError('Lo que hay en existencia tiene que ser un número, por ejemplo 24.')
      return
    }

    setOcupado(true)
    setError(null)
    try {
      const creado = await api.post<Producto>('/productos', {
        codigo_barras: borrador.codigo_barras,
        nombre: borrador.nombre.trim(),
        precio,
        costo,
        stock_actual: stock ?? 0,
        categoria: borrador.categoria.trim() || null,
        es_insumo: borrador.esInsumo,
      })
      setCargados((lista) => [creado, ...lista])
      setBorrador(null)
      setAviso(`${creado.nombre} quedó registrado. Escanea el siguiente.`)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar.')
    } finally {
      setOcupado(false)
    }
  }

  function cambiar(campo: keyof Borrador, valor: string) {
    setBorrador((actual) => (actual ? { ...actual, [campo]: valor } : actual))
  }

  return (
    <section className="tarjeta">
      <div className="catalogo">
        <p className="pista">
          Escanea un producto y el sistema busca su nombre solo. Si no lo encuentra, lo
          escribes tú — es normal que no conozca las marcas del barrio.
        </p>

        {!borrador && (
          <div className="escaneo">
            <span className="etiqueta">Escanea el producto nuevo</span>
            <input
              ref={campoCodigo}
              className="campo-grande"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              onKeyDown={escanear}
              placeholder="Escanea o escribe el código"
              autoComplete="off"
              disabled={ocupado}
            />
          </div>
        )}

        {aviso && <p className="aviso aviso-ok">{aviso}</p>}
        {error && <p className="aviso aviso-error">{error}</p>}

        {borrador && (
          <form className="alta-producto" onSubmit={guardar}>
            <span className="etiqueta">Código {borrador.codigo_barras}</span>
            {borrador.sugerido && (
              <p className="pista">Open Food Facts sugirió el nombre. Cámbialo si no cuadra.</p>
            )}

            <label className="campo">
              <span className="etiqueta">Nombre</span>
              <input
                ref={campoNombre}
                value={borrador.nombre}
                onChange={(e) => cambiar('nombre', e.target.value)}
                onFocus={(e) => e.target.select()}
              />
            </label>

            <div className="alta-fila">
              <label className="campo">
                <span className="etiqueta">Precio de venta</span>
                <input
                  className="num"
                  inputMode="numeric"
                  value={borrador.precio}
                  onChange={(e) => cambiar('precio', e.target.value)}
                />
                {leerPesos(borrador.precio) !== null && (
                  <small className="lectura-plata">
                    = {plata(leerPesos(borrador.precio) ?? 0)}
                  </small>
                )}
              </label>
              <label className="campo">
                <span className="etiqueta">Costo</span>
                <input
                  className="num"
                  inputMode="numeric"
                  value={borrador.costo}
                  onChange={(e) => cambiar('costo', e.target.value)}
                />
                {leerPesos(borrador.costo) !== null && (
                  <small className="lectura-plata">
                    = {plata(leerPesos(borrador.costo) ?? 0)}
                  </small>
                )}
              </label>
            </div>

            <div className="alta-fila">
              <label className="campo">
                <span className="etiqueta">Cuántos hay</span>
                <input
                  className="num"
                  inputMode="numeric"
                  value={borrador.stock}
                  onChange={(e) => cambiar('stock', e.target.value)}
                />
              </label>
              <label className="campo">
                <span className="etiqueta">Categoría</span>
                <input
                  value={borrador.categoria}
                  onChange={(e) => cambiar('categoria', e.target.value)}
                  placeholder="cerveza, snacks…"
                />
              </label>
            </div>

            <label className="casilla">
              <input
                type="checkbox"
                checked={borrador.esInsumo}
                onChange={(e) =>
                  setBorrador((a) => (a ? { ...a, esInsumo: e.target.checked } : a))
                }
              />
              <span>
                Es un insumo de cocina (la carne, el chorizo): se controla en inventario
                pero no se vende suelto.
              </span>
            </label>

            <div className="alta-fila">
              <button className="btn-primario" type="submit" disabled={ocupado}>
                {ocupado ? 'GUARDANDO…' : 'GUARDAR Y SEGUIR'}
              </button>
              <button
                className="btn-secundario"
                type="button"
                onClick={() => {
                  setBorrador(null)
                  setError(null)
                }}
              >
                Cancelar
              </button>
            </div>
          </form>
        )}

        {cargados.length > 0 && (
          <div className="bloque">
            <span className="etiqueta">Cargados en esta sesión · {cargados.length}</span>
            {cargados.map((p) => (
              <div key={p.id} className="fila-lista">
                <span>{p.nombre}</span>
                <span className="valor-tenue num">{plata(p.precio_de_venta)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
