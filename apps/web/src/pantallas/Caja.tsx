import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'

import { api, ErrorApi } from '../api/cliente'
import { useEventos } from '../api/eventos'
import type { DetallePedido, Pedido, Plato, Producto, TurnoCaja, Venta } from '../api/tipos'
import { cantidad as formatoCantidad, hora, leerCantidad, plata } from '../formato'
import { useSesion } from '../sesion'
import CorregirItem from './CorregirItem'
import ElegirPlato from './ElegirPlato'
import Fiados from './Fiados'
import Fondo from './Fondo'
import PanelCobro, { nombreDelMetodo, type Cobro } from './PanelCobro'
import { AbrirCaja, CerrarCaja } from './TurnoCaja'

/**
 * La caja del mostrador.
 *
 * Este archivo maneja QUÉ se vende: lo escaneado, los platos para llevar o
 * la mesa que pidió la cuenta. CÓMO se paga (método, descuento, propina,
 * fiado) vive en PanelCobro.tsx.
 */

interface Linea {
  clave: string
  producto_id?: number
  plato_id?: number
  nombre: string
  cantidad: number
  precio_unitario: number
  porPeso: boolean
}

export default function Caja() {
  const { sesion, salir } = useSesion()
  const esAdmin = sesion?.rol === 'administrador'

  // ------------------------------------------------------- lo que se vende
  const [lineas, setLineas] = useState<Linea[]>([])
  const [ultimaClave, setUltimaClave] = useState<string | null>(null)
  const [codigo, setCodigo] = useState('')
  const [pesando, setPesando] = useState<Producto | null>(null)
  const [kilos, setKilos] = useState('')
  const [eligiendoPlato, setEligiendoPlato] = useState(false)
  const [nombreParaLlevar, setNombreParaLlevar] = useState('')
  const [mesasEsperando, setMesasEsperando] = useState<Pedido[]>([])
  const [cobrandoMesa, setCobrandoMesa] = useState<Pedido | null>(null)
  const [corrigiendo, setCorrigiendo] = useState<DetallePedido | null>(null)

  // ----------------------------------------------------------- el cobro
  // Cada vez que cambia, PanelCobro arranca de cero: sin el descuento ni
  // el pago dividido de la venta anterior.
  const [vueltaDeCobro, setVueltaDeCobro] = useState(0)
  const [cobrando, setCobrando] = useState(false)
  const [ultimaVenta, setUltimaVenta] = useState<Venta | null>(null)

  // -------------------------------------------------------------- avisos
  const [error, setError] = useState<string | null>(null)
  const [nota, setNota] = useState<string | null>(null)

  // ------------------------------------------------------------- el turno
  // undefined mientras se consulta; null cuando no hay turno abierto.
  const [turno, setTurno] = useState<TurnoCaja | null | undefined>(undefined)
  const [cerrandoTurno, setCerrandoTurno] = useState(false)
  const [viendoFiados, setViendoFiados] = useState(false)

  const campoEscaneo = useRef<HTMLInputElement>(null)
  const campoKilos = useRef<HTMLInputElement>(null)
  const mesaActual = useRef(cobrandoMesa)
  mesaActual.current = cobrandoMesa

  const subtotal = cobrandoMesa
    ? cobrandoMesa.total
    : Math.round(lineas.reduce((suma, l) => suma + l.cantidad * l.precio_unitario, 0))
  const hayAlgo = cobrandoMesa !== null || lineas.length > 0
  const llevaPlatos = lineas.some((l) => l.plato_id !== undefined)

  // ------------------------------------------------------- datos en vivo
  const cargarMesas = useCallback(async () => {
    try {
      const pedidos = await api.get<Pedido[]>('/pedidos')
      setMesasEsperando(pedidos.filter((p) => p.estado === 'cuenta_pedida'))
    } catch {
      /* si falla, el aviso de conexión ya lo dice */
    }
  }, [])

  /** Vuelve a leer la mesa que se está cobrando. Si el mesero le agregó
   *  algo, el cajero tiene que verlo antes de decirle el total al cliente. */
  const refrescarMesa = useCallback(async (pedidoId: number) => {
    try {
      const actual = await api.get<Pedido>(`/pedidos/${pedidoId}`)
      const antes = mesaActual.current
      if (!antes || antes.id !== pedidoId) return
      if (actual.estado === 'pagado') {
        setCobrandoMesa(null)
        setNota(`La mesa ${actual.mesa} ya se cobró.`)
        return
      }
      if (actual.total !== antes.total) {
        setNota(
          `La mesa ${actual.mesa} cambió: ahora son ${plata(actual.total)}. Confírmalo con el cliente.`,
        )
      }
      setCobrandoMesa(actual)
    } catch {
      /* sin conexión: el cobro igual lo frena el servidor si cambió */
    }
  }, [])

  const conectado = useEventos((aviso) => {
    void cargarMesas()

    const mesa = mesaActual.current
    if (mesa && (aviso.evento === 'reconectado' || aviso.datos.pedido_id === mesa.id)) {
      void refrescarMesa(mesa.id)
    }

    // Un pedido para llevar salió de la cocina: hay que llamar al cliente.
    if (aviso.evento === 'plato_listo' && aviso.datos.para_llevar) {
      const quien = aviso.datos.cliente ? ` de ${aviso.datos.cliente}` : ''
      setNota(`Para llevar${quien}: ${aviso.datos.nombre} ya está listo.`)
    }
  })

  useEffect(() => {
    void cargarMesas()
  }, [cargarMesas])

  const cargarTurno = useCallback(() => {
    api
      .get<TurnoCaja | null>('/caja/actual')
      .then(setTurno)
      .catch(() => setTurno(null))
  }, [])

  useEffect(cargarTurno, [cargarTurno])

  // ------------------------------------------------- el foco del escáner
  // El campo de escaneo nunca pierde el foco: un escaneo que se pierde
  // porque el cursor estaba en otra parte es la falla número uno de una caja.
  // Salvo cuando el cajero está escribiendo en otro campo, o dentro de algo
  // marcado con data-conserva-foco (un diálogo, el cuaderno de fiados).
  useEffect(() => {
    const devolverFoco = (e: MouseEvent) => {
      const objetivo = e.target as HTMLElement
      if (objetivo.closest('input, label, select, textarea, [data-conserva-foco]')) return
      window.setTimeout(() => {
        if (pesando) campoKilos.current?.focus()
        else campoEscaneo.current?.focus()
      }, 0)
    }
    document.addEventListener('click', devolverFoco)
    return () => document.removeEventListener('click', devolverFoco)
  }, [pesando])

  // También cuando termina de cargar el turno: mientras dice "Abriendo la
  // caja…" el campo todavía no existe, y sin esto el primer escaneo del día
  // se perdía hasta que alguien hiciera clic.
  const hayTurno = Boolean(turno)
  useEffect(() => {
    if (pesando) campoKilos.current?.focus()
    else campoEscaneo.current?.focus()
  }, [pesando, hayTurno])

  // ------------------------------------------------------- las líneas
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

  function cambiarCantidad(clave: string, nueva: number) {
    setLineas((actuales) =>
      nueva <= 0
        ? actuales.filter((l) => l.clave !== clave)
        : actuales.map((l) => (l.clave === clave ? { ...l, cantidad: nueva } : l)),
    )
  }

  function vaciar() {
    if (
      lineas.length > 3 &&
      !window.confirm(`¿Quitar los ${lineas.length} productos y empezar de nuevo?`)
    ) {
      return
    }
    limpiar()
  }

  function agregarPlato(plato: Plato) {
    if (cobrandoMesa) {
      setError('Estás cobrando una mesa. Termina o cancela antes de agregar platos.')
      return
    }
    agregar(
      {
        clave: `plato:${plato.id}`,
        plato_id: plato.id,
        nombre: plato.nombre,
        precio_unitario: plato.precio,
        porPeso: false,
      },
      1,
    )
  }

  async function alEscanear(e: KeyboardEvent<HTMLInputElement>) {
    // Supr con el campo vacío quita uno de lo último que se escaneó: el
    // error más común es pasar el mismo producto dos veces por el lector.
    if (e.key === 'Delete' && !codigo && ultimaClave && !cobrandoMesa) {
      const ultima = lineas.find((l) => l.clave === ultimaClave)
      if (ultima) cambiarCantidad(ultima.clave, ultima.porPeso ? 0 : ultima.cantidad - 1)
      return
    }
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
          porPeso: false,
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

    const kg = leerCantidad(kilos)
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
        porPeso: true,
      },
      kg,
    )
    setPesando(null)
  }

  // ------------------------------------------------------- cobrar
  /** Deja la caja lista para el siguiente cliente. */
  function limpiar() {
    setLineas([])
    setCobrandoMesa(null)
    setUltimaClave(null)
    setNota(null)
    setNombreParaLlevar('')
    setEligiendoPlato(false)
    setVueltaDeCobro((n) => n + 1)
    campoEscaneo.current?.focus()
  }

  async function cobrar(cobro: Cobro) {
    setCobrando(true)
    setError(null)
    try {
      const venta = cobrandoMesa
        ? await api.post<Venta>(`/pedidos/${cobrandoMesa.id}/cobrar`, {
            ...cobro,
            total_esperado: cobrandoMesa.total,
          })
        : await api.post<Venta>('/ventas', {
            ...cobro,
            tipo: 'mostrador',
            nombre_para_llevar: llevaPlatos ? nombreParaLlevar.trim() || null : null,
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
      // La mesa cambió mientras se cobraba: se muestra la cuenta nueva.
      if (fallo instanceof ErrorApi && fallo.estado === 409 && cobrandoMesa) {
        void refrescarMesa(cobrandoMesa.id)
      }
      // Alguien cerró la caja desde otro lado.
      if (fallo instanceof ErrorApi && fallo.message.startsWith('Abre la caja')) {
        cargarTurno()
      }
    } finally {
      setCobrando(false)
    }
  }

  async function anularUltima() {
    if (!ultimaVenta) return
    const motivo = window.prompt(
      `Vas a anular la venta #${ultimaVenta.id} por ${plata(ultimaVenta.a_cobrar)}.\n\n¿Por qué?`,
    )
    if (!motivo?.trim()) return

    try {
      await api.post(`/ventas/${ultimaVenta.id}/anular`, { motivo: motivo.trim() })
      setUltimaVenta(null)
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo anular.')
    }
  }

  if (turno === undefined) return <p className="cargando">Abriendo la caja…</p>
  if (turno === null) return <AbrirCaja alAbrir={setTurno} />

  return (
    <div className="caja">
      <Fondo />
      {cerrandoTurno && (
        <CerrarCaja
          alCerrar={() => {
            setCerrandoTurno(false)
            setTurno(null)
          }}
          cancelar={() => setCerrandoTurno(false)}
        />
      )}

      {viendoFiados && (
        <div className="turno-fondo" data-conserva-foco>
          <div className="panel-flotante">
            <div className="opcion-cabeza">
              <h2 className="tarjeta-titulo">Fiados</h2>
              <button className="btn-secundario btn-angosto" onClick={() => setViendoFiados(false)}>
                Volver a la caja
              </button>
            </div>
            <Fiados esAdmin={esAdmin} />
          </div>
        </div>
      )}

      {corrigiendo && cobrandoMesa && (
        <CorregirItem
          pedidoId={cobrandoMesa.id}
          detalle={corrigiendo}
          pideCodigo={!esAdmin && corrigiendo.agregado_por_id !== sesion?.id}
          alTerminar={(actualizado) => {
            setCobrandoMesa(actualizado)
            setCorrigiendo(null)
            setNota(`Mesa ${actualizado.mesa} corregida: ahora son ${plata(actualizado.total)}.`)
          }}
          cancelar={() => setCorrigiendo(null)}
        />
      )}

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
              <div className="escaneo-fila">
                <input
                  ref={campoEscaneo}
                  className="campo-grande"
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  onKeyDown={alEscanear}
                  placeholder="Escanea o escribe el código"
                  autoComplete="off"
                />
                <button
                  className={`btn-secundario btn-angosto ${eligiendoPlato ? 'activo' : ''}`}
                  onClick={() => setEligiendoPlato((v) => !v)}
                >
                  Platos
                </button>
              </div>
              <span className="pista">
                El cursor vuelve aquí solo · Supr quita uno de lo último que escaneaste
              </span>
            </div>
          )}

          {eligiendoPlato && (
            <ElegirPlato alElegir={agregarPlato} cerrar={() => setEligiendoPlato(false)} />
          )}

          {error && <p className="aviso aviso-error">{error}</p>}
          {nota && <p className="aviso aviso-atencion">{nota}</p>}

          {cobrandoMesa && (
            <p className="aviso aviso-atencion">
              Cobrando la mesa {cobrandoMesa.mesa}.{' '}
              <button className="btn-peligro" onClick={limpiar}>
                Cancelar
              </button>
            </p>
          )}

          {llevaPlatos && (
            <label className="para-llevar">
              <span>Para llevar · ¿a nombre de quién?</span>
              <input
                value={nombreParaLlevar}
                onChange={(e) => setNombreParaLlevar(e.target.value)}
                placeholder="Para llamarlo cuando esté listo"
                maxLength={60}
              />
            </label>
          )}

          {cobrandoMesa ? (
            <TablaDeMesa
              mesa={cobrandoMesa}
              alCorregir={(detalle) => setCorrigiendo(detalle)}
            />
          ) : (
            <table className="lineas">
              <thead>
                <tr>
                  <th>Producto</th>
                  <th className="num">Cant.</th>
                  <th className="num">Precio</th>
                  <th className="num">Subtotal</th>
                  <th className="acciones">
                    {lineas.length > 0 && (
                      <button className="btn-peligro" onClick={vaciar}>
                        Vaciar
                      </button>
                    )}
                  </th>
                </tr>
              </thead>
              <tbody>
                {lineas.length === 0 && (
                  <tr>
                    <td colSpan={5} className="vacio">
                      Escanea el primer producto para empezar.
                    </td>
                  </tr>
                )}
                {lineas.map((l) => (
                  <tr key={l.clave} className={l.clave === ultimaClave ? 'fila-nueva' : ''}>
                    <td>{l.nombre}</td>
                    <td className="num">
                      {l.porPeso ? (
                        formatoCantidad(l.cantidad)
                      ) : (
                        <span className="stepper stepper-chico">
                          <button
                            onClick={() => cambiarCantidad(l.clave, l.cantidad - 1)}
                            aria-label={`Quitar uno de ${l.nombre}`}
                          >
                            −
                          </button>
                          <span className="stepper-cantidad num">
                            {formatoCantidad(l.cantidad)}
                          </span>
                          <button
                            onClick={() => cambiarCantidad(l.clave, l.cantidad + 1)}
                            aria-label={`Agregar uno de ${l.nombre}`}
                          >
                            +
                          </button>
                        </span>
                      )}
                    </td>
                    <td className="num">{plata(l.precio_unitario)}</td>
                    <td className="num">{plata(l.cantidad * l.precio_unitario)}</td>
                    <td className="acciones">
                      <button
                        className="btn-quitar"
                        onClick={() => cambiarCantidad(l.clave, 0)}
                        aria-label={`Quitar ${l.nombre} de la venta`}
                        title="Quitar de la venta"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <aside className="caja-der">
          <PanelCobro
            key={vueltaDeCobro}
            subtotal={subtotal}
            esMesa={cobrandoMesa !== null}
            hayAlgo={hayAlgo}
            cobrando={cobrando}
            esAdmin={esAdmin}
            alCobrar={(cobro) => void cobrar(cobro)}
          />

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
              Cobrado #{ultimaVenta.id} · {plata(ultimaVenta.a_cobrar)} ·{' '}
              {ultimaVenta.pagos.length === 0
                ? 'cortesía'
                : nombreDelMetodo(ultimaVenta.metodo_pago).toLowerCase()}
            </span>
            <button className="btn-peligro" onClick={() => void anularUltima()}>
              Anular última venta
            </button>
          </>
        ) : (
          <span className="pista">Todavía no has cobrado nada en esta sesión.</span>
        )}
        <span className="caja-pie-der">
          <button className="btn-secundario btn-angosto" onClick={() => setViendoFiados(true)}>
            Fiados
          </button>
          <span className="pista">Caja abierta desde {hora(turno.hora_apertura)}</span>
          <button className="btn-secundario btn-angosto" onClick={() => setCerrandoTurno(true)}>
            Cerrar caja
          </button>
        </span>
      </footer>
    </div>
  )
}

/** Lo que pidió la mesa que se está cobrando. No se edita como lo
 *  escaneado: quitar algo de una mesa deja registro, así que pasa por el
 *  diálogo de corregir. */
function TablaDeMesa({
  mesa,
  alCorregir,
}: {
  mesa: Pedido
  alCorregir: (detalle: DetallePedido) => void
}) {
  return (
    <table className="lineas">
      <thead>
        <tr>
          <th>Producto</th>
          <th className="num">Cant.</th>
          <th className="num">Precio</th>
          <th className="num">Subtotal</th>
          <th className="acciones" />
        </tr>
      </thead>
      <tbody>
        {mesa.detalles.map((d) => (
          <tr key={d.id}>
            <td>
              {d.nombre}
              {d.notas && <small className="nota-plato"> · {d.notas}</small>}
            </td>
            <td className="num">{formatoCantidad(d.cantidad)}</td>
            <td className="num">{plata(d.precio_unitario)}</td>
            <td className="num">{plata(d.subtotal)}</td>
            <td className="acciones">
              <button className="btn-corregir" onClick={() => alCorregir(d)}>
                Corregir
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
