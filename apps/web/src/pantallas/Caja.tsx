import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'

import { api } from '../api/cliente'
import { useEventos } from '../api/eventos'
import type { MetodoPago, Pedido, Producto, Venta } from '../api/tipos'
import { cantidad as formatoCantidad, hora, plata } from '../formato'
import { useSesion } from '../sesion'
import Fondo from './Fondo'

interface Linea {
  clave: string
  producto_id?: number
  plato_id?: number
  nombre: string
  cantidad: number
  precio_unitario: number
}

const METODOS: { valor: MetodoPago; texto: string }[] = [
  { valor: 'efectivo', texto: 'Efectivo' },
  { valor: 'nequi', texto: 'Nequi' },
  { valor: 'daviplata', texto: 'Daviplata' },
  { valor: 'tarjeta', texto: 'Tarjeta' },
]

export default function Caja() {
  const { sesion, salir } = useSesion()
  const [lineas, setLineas] = useState<Linea[]>([])
  const [ultimaClave, setUltimaClave] = useState<string | null>(null)
  const [codigo, setCodigo] = useState('')
  const [pesando, setPesando] = useState<Producto | null>(null)
  const [kilos, setKilos] = useState('')
  const [metodoPago, setMetodoPago] = useState<MetodoPago>('efectivo')
  const [recibido, setRecibido] = useState('')
  const [mesasEsperando, setMesasEsperando] = useState<Pedido[]>([])
  const [cobrandoMesa, setCobrandoMesa] = useState<Pedido | null>(null)
  const [ultimaVenta, setUltimaVenta] = useState<Venta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cobrando, setCobrando] = useState(false)

  const campoEscaneo = useRef<HTMLInputElement>(null)
  const campoKilos = useRef<HTMLInputElement>(null)

  const total = cobrandoMesa
    ? cobrandoMesa.total
    : Math.round(lineas.reduce((suma, l) => suma + l.cantidad * l.precio_unitario, 0))

  const vuelto = metodoPago === 'efectivo' && recibido ? Number(recibido) - total : null

  const cargarMesas = useCallback(async () => {
    try {
      const pedidos = await api.get<Pedido[]>('/pedidos')
      setMesasEsperando(pedidos.filter((p) => p.estado === 'cuenta_pedida'))
    } catch {
      /* si falla, el aviso de conexión ya lo dice */
    }
  }, [])

  const conectado = useEventos(() => void cargarMesas())

  useEffect(() => {
    void cargarMesas()
  }, [cargarMesas])

  // El campo de escaneo nunca pierde el foco: un escaneo que se pierde
  // porque el cursor estaba en otra parte es la falla número uno de una caja.
  useEffect(() => {
    const devolverFoco = (e: MouseEvent) => {
      if ((e.target as HTMLElement).closest('input')) return
      window.setTimeout(() => {
        if (pesando) campoKilos.current?.focus()
        else campoEscaneo.current?.focus()
      }, 0)
    }
    document.addEventListener('click', devolverFoco)
    return () => document.removeEventListener('click', devolverFoco)
  }, [pesando])

  useEffect(() => {
    if (pesando) campoKilos.current?.focus()
    else campoEscaneo.current?.focus()
  }, [pesando])

  function agregar(linea: Omit<Linea, 'cantidad'>, cuanto: number) {
    setLineas((actuales) => {
      const existente = actuales.find((l) => l.clave === linea.clave)
      if (existente) {
        return actuales.map((l) =>
          l.clave === linea.clave ? { ...l, cantidad: l.cantidad + cuanto } : l,
        )
      }
      return [...actuales, { ...linea, cantidad: cuanto }]
    })
    setUltimaClave(linea.clave)
    setError(null)
  }

  async function alEscanear(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    const leido = codigo.trim()
    setCodigo('')
    if (!leido) return

    if (cobrandoMesa) {
      setError('Estás cobrando una mesa. Termina o cancela antes de escanear.')
      return
    }

    try {
      const producto = await api.get<Producto>(
        `/productos/codigo/${encodeURIComponent(leido)}`,
      )
      if (producto.tipo_venta === 'peso') {
        setPesando(producto)
        setKilos('')
        return
      }
      agregar(
        {
          clave: `producto:${producto.id}`,
          producto_id: producto.id,
          nombre: producto.nombre,
          precio_unitario: producto.precio_de_venta,
        },
        1,
      )
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo leer ese código.')
    }
  }

  function confirmarPeso(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      setPesando(null)
      return
    }
    if (e.key !== 'Enter' || !pesando) return

    const kg = Number(kilos.replace(',', '.'))
    if (!kg || kg <= 0) {
      setError('Escribe cuántos kilos, por ejemplo 0,4')
      return
    }
    agregar(
      {
        clave: `producto:${pesando.id}`,
        producto_id: pesando.id,
        nombre: pesando.nombre,
        precio_unitario: pesando.precio_de_venta,
      },
      kg,
    )
    setPesando(null)
  }

  function limpiar() {
    setLineas([])
    setCobrandoMesa(null)
    setUltimaClave(null)
    setRecibido('')
    setMetodoPago('efectivo')
  }

  const cobrar = useCallback(async () => {
    if (cobrando) return
    if (!cobrandoMesa && lineas.length === 0) return

    setCobrando(true)
    setError(null)
    try {
      const venta = cobrandoMesa
        ? await api.post<Venta>(`/pedidos/${cobrandoMesa.id}/cobrar`, {
            metodo_pago: metodoPago,
          })
        : await api.post<Venta>('/ventas', {
            tipo: 'mostrador',
            metodo_pago: metodoPago,
            items: lineas.map((l) => ({
              producto_id: l.producto_id,
              plato_id: l.plato_id,
              cantidad: l.cantidad,
            })),
          })

      setUltimaVenta(venta)
      limpiar()
      void cargarMesas()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cobrar.')
    } finally {
      setCobrando(false)
    }
  }, [cobrando, cobrandoMesa, lineas, metodoPago, cargarMesas])

  // F12 cobra sin soltar el lector ni tocar el mouse.
  useEffect(() => {
    const atajo = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'F12') {
        e.preventDefault()
        void cobrar()
      }
    }
    window.addEventListener('keydown', atajo)
    return () => window.removeEventListener('keydown', atajo)
  }, [cobrar])

  async function anularUltima() {
    if (!ultimaVenta) return
    const motivo = window.prompt(
      `Vas a anular la venta #${ultimaVenta.id} por ${plata(ultimaVenta.total)}.\n\n¿Por qué?`,
    )
    if (!motivo) return

    try {
      await api.post(`/ventas/${ultimaVenta.id}/anular`, { motivo })
      setUltimaVenta(null)
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo anular.')
    }
  }

  const filas = cobrandoMesa
    ? cobrandoMesa.detalles.map((d) => ({
        clave: `mesa:${d.id}`,
        nombre: d.nombre,
        cantidad: d.cantidad,
        precio_unitario: d.precio_unitario,
      }))
    : lineas

  return (
    <div className="caja">
      <Fondo />
      <header className="barra">
        <span className="marca">EL CAMPUS</span>
        <span>Caja · {sesion?.nombre}</span>
        <span className="der">
          <span className={conectado ? 'chip-ok' : 'chip-mal'}>
            ● {conectado ? 'Conectado' : 'Sin conexión en vivo'}
          </span>
          <button className="btn-peligro" onClick={salir}>
            Salir
          </button>
        </span>
      </header>

      <div className="caja-cuerpo">
        <section className="caja-izq">
          {pesando ? (
            <div className="peso-panel">
              <span className="etiqueta">
                {pesando.nombre} · {plata(pesando.precio_de_venta)} por kilo
              </span>
              <input
                ref={campoKilos}
                className="campo-grande"
                value={kilos}
                onChange={(e) => setKilos(e.target.value)}
                onKeyDown={confirmarPeso}
                placeholder="¿Cuántos kilos? Ej: 0,4"
                inputMode="decimal"
              />
              <span className="pista">Enter para agregar · Esc para cancelar</span>
            </div>
          ) : (
            <div className="escaneo">
              <span className="etiqueta">Escanea el producto</span>
              <input
                ref={campoEscaneo}
                className="campo-grande"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                onKeyDown={alEscanear}
                placeholder="Escanea o escribe el código"
                autoComplete="off"
              />
              <span className="pista">El cursor vuelve aquí solo.</span>
            </div>
          )}

          {error && <p className="aviso aviso-error">{error}</p>}

          {cobrandoMesa && (
            <p className="aviso aviso-atencion">
              Cobrando la mesa {cobrandoMesa.mesa}.{' '}
              <button className="btn-peligro" onClick={() => setCobrandoMesa(null)}>
                Cancelar
              </button>
            </p>
          )}

          <table className="lineas">
            <thead>
              <tr>
                <th>Producto</th>
                <th className="num">Cant.</th>
                <th className="num">Precio</th>
                <th className="num">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {filas.length === 0 && (
                <tr>
                  <td colSpan={4} className="vacio">
                    Escanea el primer producto para empezar.
                  </td>
                </tr>
              )}
              {filas.map((l) => (
                <tr key={l.clave} className={l.clave === ultimaClave ? 'fila-nueva' : ''}>
                  <td>{l.nombre}</td>
                  <td className="num">{formatoCantidad(l.cantidad)}</td>
                  <td className="num">{plata(l.precio_unitario)}</td>
                  <td className="num">{plata(l.cantidad * l.precio_unitario)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <aside className="caja-der">
          <div className="total-caja">
            <span className="etiqueta">Total</span>
            <span className="total-valor num">{plata(total)}</span>
          </div>

          <div className="pagos">
            {METODOS.map((m) => (
              <button
                key={m.valor}
                className={`pago ${metodoPago === m.valor ? 'activo' : ''}`}
                onClick={() => setMetodoPago(m.valor)}
              >
                {m.texto}
              </button>
            ))}
          </div>

          {metodoPago === 'efectivo' && (
            <div className="vuelto">
              <label className="fila">
                <span>Recibido</span>
                <input
                  className="campo-recibido num"
                  value={recibido}
                  onChange={(e) => setRecibido(e.target.value)}
                  inputMode="numeric"
                  placeholder="0"
                />
              </label>
              {vuelto !== null && vuelto >= 0 && (
                <div className="fila destacada">
                  <span>Vuelto</span>
                  <span className="num">{plata(vuelto)}</span>
                </div>
              )}
            </div>
          )}

          <button
            className="btn-cobrar"
            onClick={() => void cobrar()}
            disabled={cobrando || total === 0}
          >
            COBRAR <small>F12</small>
          </button>

          {mesasEsperando.map((pedido) => (
            <button
              key={pedido.id}
              className="mesa-esperando"
              onClick={() => {
                limpiar()
                setCobrandoMesa(pedido)
              }}
            >
              <b>Mesa {pedido.mesa} pidió la cuenta</b>
              <small className="num">
                {pedido.detalles.length} productos · {plata(pedido.total)}
                {pedido.hora_cuenta_pedida && ` · ${hora(pedido.hora_cuenta_pedida)}`}
              </small>
            </button>
          ))}
        </aside>
      </div>

      <footer className="caja-pie">
        {ultimaVenta ? (
          <>
            <span className="chip-ok">
              Cobrado #{ultimaVenta.id} · {plata(ultimaVenta.total)}
            </span>
            <button className="btn-peligro" onClick={() => void anularUltima()}>
              Anular última venta
            </button>
          </>
        ) : (
          <span className="pista">Todavía no has cobrado nada en esta sesión.</span>
        )}
      </footer>
    </div>
  )
}
