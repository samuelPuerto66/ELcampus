import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  enviarPedido,
  nuevaClave,
  quitarDeLaBandeja,
  useBandeja,
  type Envio,
  type LineaEnvio,
} from '../api/bandeja'
import { api, SinConexion } from '../api/cliente'
import { useEventos } from '../api/eventos'
import type { DetallePedido, Pedido, Plato, Producto } from '../api/tipos'
import { cantidad as formatoCantidad, hora, plata } from '../formato'
import { useSesion } from '../sesion'
import CorregirItem from './CorregirItem'
import Fondo from './Fondo'
import NotaDelPlato from './NotaDelPlato'

/** Una línea de lo que el mesero va anotando. Todavía no existe en el
 *  servidor: vive en el teléfono hasta que se confirma el pedido.
 *
 *  `clave` identifica la línea, no el producto: puede haber dos líneas de
 *  picada, una con nota y otra sin. Para saber de qué producto es, está
 *  `queEs()`. */
interface Linea extends LineaEnvio {
  clave: string
}

/** El borrador se guarda por mesa. Si al mesero se le bloquea la pantalla o
 *  se sale sin querer, lo que llevaba anotado sigue ahí. */
const llaveBorrador = (mesa: string) => `elcampus.borrador.mesa.${mesa}`

function leerBorrador(mesa: string): Linea[] {
  try {
    const guardado = localStorage.getItem(llaveBorrador(mesa))
    return guardado ? (JSON.parse(guardado) as Linea[]) : []
  } catch {
    return []
  }
}

function guardarBorrador(mesa: string, lineas: Linea[]) {
  try {
    if (lineas.length === 0) localStorage.removeItem(llaveBorrador(mesa))
    else localStorage.setItem(llaveBorrador(mesa), JSON.stringify(lineas))
  } catch {
    // Sin espacio o en modo privado: se sigue trabajando en memoria.
  }
}

/** El menú se guarda en el celular cada vez que se carga bien. Si el mesero
 *  abre una mesa justo cuando no hay señal, igual puede tomar el pedido. */
const LLAVE_MENU = 'elcampus.menu'

interface Menu {
  platos: Plato[]
  productos: Producto[]
}

function leerMenu(): Menu | null {
  try {
    const guardado = localStorage.getItem(LLAVE_MENU)
    return guardado ? (JSON.parse(guardado) as Menu) : null
  } catch {
    return null
  }
}

/** De qué producto o plato es una línea, sin importar la nota. */
const queEs = (l: { producto_id?: number; plato_id?: number }) =>
  l.plato_id ? `plato-${l.plato_id}` : `producto-${l.producto_id}`

const totalDe = (lineas: LineaEnvio[]) =>
  lineas.reduce((suma, l) => suma + l.precio * l.cantidad, 0)

export default function Mesa() {
  const { numero = '' } = useParams()
  const navegar = useNavigate()

  const [pedido, setPedido] = useState<Pedido | null>(null)
  const [cargando, setCargando] = useState(true)
  const [sinSenal, setSinSenal] = useState(false)
  const [menu, setMenu] = useState<Menu>(() => leerMenu() ?? { platos: [], productos: [] })
  const [borrador, setBorrador] = useState<Linea[]>(() => leerBorrador(numero))
  const [eligiendo, setEligiendo] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const [viendoCuenta, setViendoCuenta] = useState(false)
  const [subiendo, setSubiendo] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [listo, setListo] = useState<string | null>(null)
  // La línea del borrador a la que se le está poniendo nota.
  const [conNota, setConNota] = useState<Linea | null>(null)
  // Lo ya enviado que se está corrigiendo.
  const [corrigiendo, setCorrigiendo] = useState<DetallePedido | null>(null)
  const { sesion } = useSesion()

  const bandeja = useBandeja()
  const deEstaMesa = useMemo(
    () => bandeja.filter((e) => e.mesa === Number(numero)),
    [bandeja, numero],
  )
  const enEspera = deEstaMesa.filter((e) => !e.rechazo)
  const rechazados = deEstaMesa.filter((e) => e.rechazo)

  const cargar = useCallback(async () => {
    try {
      setPedido(await api.get<Pedido | null>(`/pedidos/mesa/${numero}`))
      setSinSenal(false)
    } catch (fallo) {
      if (fallo instanceof SinConexion) setSinSenal(true)
      else setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar la mesa.')
    } finally {
      setCargando(false)
    }
  }, [numero])

  useEffect(() => {
    void cargar()
    Promise.all([api.get<Plato[]>('/platos'), api.get<Producto[]>('/productos')])
      .then(([platos, productos]) => {
        const nuevo = { platos, productos }
        setMenu(nuevo)
        try {
          localStorage.setItem(LLAVE_MENU, JSON.stringify(nuevo))
        } catch {
          /* sin espacio: se usa el que hay en memoria */
        }
      })
      .catch(() => undefined)
  }, [cargar])

  // La mesa se vuelve a leer cuando algo le pasa: la cocina marcó un plato,
  // la caja la cobró, o llegó un pedido que estaba esperando señal.
  useEventos((aviso) => {
    if (aviso.evento === 'reconectado' || aviso.datos.mesa === Number(numero)) {
      void cargar()
    }
  })

  // Cuando sale algo de la bandeja es porque llegó a la caja: se vuelve a
  // leer la mesa para mostrarlo en "Ya enviado".
  const esperandoAntes = useRef(enEspera.length)
  const confirmandoAhora = useRef(false)
  useEffect(() => {
    if (enEspera.length < esperandoAntes.current) {
      void cargar()
      // Si salió porque el mesero acaba de confirmar, ese aviso ya lo da
      // confirmar(); este es para lo que llegó solo, más tarde.
      if (!confirmandoAhora.current) setListo('Llegó a la caja lo que estaba esperando señal.')
    }
    esperandoAntes.current = enEspera.length
  }, [enEspera.length, cargar])

  useEffect(() => {
    guardarBorrador(numero, borrador)
  }, [numero, borrador])

  // Los avisos se van solos. El mesero está de pie con el celular en la
  // mano: un mensaje que se queda pegado le tapa la mesa que está mirando.
  useEffect(() => {
    if (!listo) return
    const reloj = setTimeout(() => setListo(null), 3500)
    return () => clearTimeout(reloj)
  }, [listo])

  useEffect(() => {
    if (!error) return
    const reloj = setTimeout(() => setError(null), 6000)
    return () => clearTimeout(reloj)
  }, [error])

  const totalBorrador = useMemo(() => totalDe(borrador), [borrador])
  const totalEnEspera = enEspera.reduce((suma, e) => suma + totalDe(e.lineas), 0)

  // Cuánto lleva de cada cosa, sumando sus líneas, para marcarlo en el menú.
  const yaElegido = useMemo(() => {
    const cuantos = new Map<string, number>()
    for (const l of borrador) cuantos.set(queEs(l), (cuantos.get(queEs(l)) ?? 0) + l.cantidad)
    return cuantos
  }, [borrador])

  /** Tocar un producto lo selecciona y ya. Volver a tocarlo no suma nada:
   *  la cantidad se maneja solo con los botones + y −, que es donde el
   *  mesero puede ver lo que está haciendo antes de subirlo.
   *
   *  La excepción: si todo lo que hay de ese plato ya lleva nota, tocarlo
   *  abre una línea nueva sin nota ("una sin cebolla y otra normal"). */
  function anotar(item: LineaEnvio) {
    setBorrador((lineas) => {
      const haySinNota = lineas.some((l) => queEs(l) === queEs(item) && !l.notas)
      return haySinNota ? lineas : [...lineas, { ...item, clave: nuevaClave() }]
    })
    setListo(null)
  }

  /** Pone la nota a toda la línea, o la parte: una unidad se va a una línea
   *  nueva con la nota y el resto queda como estaba. */
  function guardarNota(linea: Linea, nota: string | null, soloUno: boolean) {
    setBorrador((lineas) => {
      if (!soloUno) {
        return lineas.map((l) =>
          l.clave === linea.clave ? { ...l, notas: nota ?? undefined } : l,
        )
      }
      const resto = lineas.map((l) =>
        l.clave === linea.clave ? { ...l, cantidad: l.cantidad - 1 } : l,
      )
      return [...resto, { ...linea, clave: nuevaClave(), cantidad: 1, notas: nota ?? undefined }]
    })
    setConNota(null)
  }

  function cambiarCantidad(clave: string, nueva: number) {
    setBorrador((lineas) =>
      nueva <= 0
        ? lineas.filter((l) => l.clave !== clave)
        : lineas.map((l) => (l.clave === clave ? { ...l, cantidad: nueva } : l)),
    )
  }

  async function confirmar() {
    setSubiendo(true)
    setError(null)
    const lineas: LineaEnvio[] = borrador.map(({ clave: _, ...linea }) => linea)

    // enviarPedido lo guarda en la bandeja del celular antes de tocar la
    // red. Desde ese momento ya está a salvo, así que el borrador se limpia
    // de una: si se esperara la respuesta, durante esos segundos el pedido
    // aparecería dos veces en pantalla y sumado dos veces al total.
    confirmandoAhora.current = true
    const envio = enviarPedido(Number(numero), lineas)
    setBorrador([])
    setConfirmando(false)
    setEligiendo(false)
    const resultado = await envio.finally(() => {
      confirmandoAhora.current = false
    })
    setSubiendo(false)

    if (resultado.estado === 'enviado') {
      setPedido(resultado.pedido)
      setSinSenal(false)
      setListo('Pedido enviado a la caja.')
    } else if (resultado.estado === 'en_cola') {
      setSinSenal(true)
    } else {
      setError(resultado.motivo)
    }
  }

  /** Un pedido que el servidor no aceptó vuelve a lo anotado, para que el
   *  mesero lo corrija en vez de perderlo. */
  function volverAAnotar(envio: Envio) {
    setBorrador((actuales) => [
      ...actuales,
      ...envio.lineas.map((linea) => ({ ...linea, clave: nuevaClave() })),
    ])
    quitarDeLaBandeja(envio.clave)
  }

  /** Abre la cuenta para leérsela al cliente. La primera vez además le
   *  avisa a la caja; después solo la vuelve a mostrar, porque el cliente
   *  bien puede preguntar dos veces cuánto va. */
  async function verCuenta() {
    if (!pedido) return
    setViendoCuenta(true)

    if (pedido.estado === 'cuenta_pedida') return

    setSubiendo(true)
    try {
      setPedido(await api.post<Pedido>(`/pedidos/${pedido.id}/pedir-cuenta`))
      setListo('La caja ya tiene la cuenta.')
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo avisar a la caja.')
    } finally {
      setSubiendo(false)
    }
  }

  if (cargando) return <p className="cargando">Cargando la mesa…</p>

  const ocupada = pedido !== null
  const totalMesa = (pedido?.total ?? 0) + totalEnEspera + totalBorrador

  return (
    <div className="celular-pantalla">
      <Fondo />
      <header className="barra">
        <button className="btn-peligro" onClick={() => navegar('/mesas')}>
          ← Mesas
        </button>
        <span className="marca">MESA {numero}</span>
        <span className="der pista">
          {sinSenal && !ocupada
            ? 'Sin señal'
            : !ocupada
              ? 'Libre'
              : pedido!.estado === 'cuenta_pedida'
                ? 'Cuenta pedida'
                : `Abierta ${hora(pedido!.hora_apertura)}`}
        </span>
      </header>

      <div className="celular-cuerpo">
        {error && <p className="aviso aviso-error">{error}</p>}
        {listo && <p className="aviso aviso-ok">{listo}</p>}
        {sinSenal && (
          <p className="aviso aviso-atencion">
            Sin señal con la caja. Sigue anotando: lo que confirmes se guarda en el
            celular y se envía solo cuando vuelva el WiFi.
          </p>
        )}

        {/* ---------------------------------------- lo que ya está en la caja */}
        {ocupada && pedido!.detalles.length > 0 && (
          <section className="bloque">
            <span className="etiqueta">Ya enviado a la caja</span>
            {pedido!.detalles.map((detalle) => (
              <div key={detalle.id} className="item-pedido enviado">
                <span className="item-nombre">
                  {detalle.nombre}
                  {detalle.plato_id !== null && detalle.estado_cocina === 'listo' && (
                    <span className="chip-listo">Listo para recoger</span>
                  )}
                  <small className="num">
                    {plata(detalle.precio_unitario)}
                    {detalle.notas ? ` · ${detalle.notas}` : ''}
                  </small>
                </span>
                <span className="cantidad-fija num">×{formatoCantidad(detalle.cantidad)}</span>
                <button className="btn-corregir" onClick={() => setCorrigiendo(detalle)}>
                  Corregir
                </button>
              </div>
            ))}
          </section>
        )}

        {/* ------------------------------- confirmado pero sin llegar todavía */}
        {enEspera.length > 0 && (
          <section className="bloque">
            <span className="etiqueta etiqueta-espera">
              {subiendo ? 'Enviando a la caja…' : 'Esperando señal · se envía solo'}
            </span>
            {enEspera.map((envio) =>
              envio.lineas.map((linea, i) => (
                <div key={`${envio.clave}-${i}`} className="item-pedido en-espera">
                  <span className="item-nombre">
                    {linea.nombre}
                    <small className="num">
                      {plata(linea.precio)}
                      {linea.notas && ` · ${linea.notas}`} · anotado {hora(envio.creado)}
                    </small>
                  </span>
                  <span className="cantidad-fija num">×{formatoCantidad(linea.cantidad)}</span>
                </div>
              )),
            )}
          </section>
        )}

        {/* ------------------------------------- lo que la caja no aceptó */}
        {rechazados.map((envio) => (
          <section key={envio.clave} className="bloque rechazado">
            <p className="aviso aviso-error">
              Este pedido no entró: {envio.rechazo}
            </p>
            {envio.lineas.map((linea, i) => (
              <div key={i} className="item-pedido enviado">
                <span className="item-nombre">{linea.nombre}</span>
                <span className="cantidad-fija num">×{formatoCantidad(linea.cantidad)}</span>
              </div>
            ))}
            <div className="fila-botones">
              <button className="btn-secundario" onClick={() => volverAAnotar(envio)}>
                Volver a anotarlo
              </button>
              <button className="btn-peligro" onClick={() => quitarDeLaBandeja(envio.clave)}>
                Descartar
              </button>
            </div>
          </section>
        ))}

        {/* ------------------------------------------ lo que se está anotando */}
        <section className="bloque">
          <span className="etiqueta">
            {borrador.length > 0 ? 'Por enviar' : 'Nada anotado todavía'}
          </span>

          {borrador.length === 0 && (
            <p className="pista">
              {ocupada || enEspera.length > 0
                ? 'Toca «Agregar algo más» para anotar otra ronda.'
                : 'Esta mesa sigue libre. Se ocupa cuando envíes el primer pedido.'}
            </p>
          )}

          {borrador.map((linea) => (
            <div key={linea.clave} className="item-pedido">
              <span className="item-nombre">
                {linea.nombre}
                <small className="num">
                  {plata(linea.precio)}
                  {linea.notas && <span className="nota-plato"> · {linea.notas}</span>}
                </small>
                {/* La nota es para la cocina: solo los platos la llevan. */}
                {linea.plato_id && (
                  <button className="btn-nota" onClick={() => setConNota(linea)}>
                    {linea.notas ? 'Cambiar nota' : '+ Nota'}
                  </button>
                )}
              </span>
              <span className="stepper">
                <button
                  onClick={() => cambiarCantidad(linea.clave, linea.cantidad - 1)}
                  aria-label={`Quitar uno de ${linea.nombre}`}
                >
                  −
                </button>
                <span className="stepper-cantidad num">{formatoCantidad(linea.cantidad)}</span>
                <button
                  onClick={() => cambiarCantidad(linea.clave, linea.cantidad + 1)}
                  aria-label={`Agregar uno de ${linea.nombre}`}
                >
                  +
                </button>
              </span>
            </div>
          ))}
        </section>

        <div className="total-mesa">
          <span className="etiqueta">Total de la mesa</span>
          <span className="total-mesa-valor num">{plata(totalMesa)}</span>
        </div>
      </div>

      {/* ------------------------------------------------------ el menú */}
      {eligiendo && (
        <div className="elector">
          <div className="elector-barra">
            <span className="etiqueta">¿Qué pidió?</span>
            <button className="btn-peligro" onClick={() => setEligiendo(false)}>
              Cerrar
            </button>
          </div>
          <div className="elector-lista">
            {menu.platos.length === 0 && menu.productos.length === 0 && (
              <p className="pista">
                No se pudo cargar el menú y no hay uno guardado en este celular. Acércate
                al WiFi y vuelve a abrir la mesa.
              </p>
            )}
            {menu.platos.map((plato) => {
              const lleva = yaElegido.get(`plato-${plato.id}`)
              return (
                <button
                  key={`plato-${plato.id}`}
                  className={`tarjeta-item ${plato.tipo === 'especial' ? 'especial' : ''} ${
                    lleva ? 'elegido' : ''
                  }`}
                  aria-pressed={Boolean(lleva)}
                  onClick={() =>
                    anotar({ plato_id: plato.id, nombre: plato.nombre, precio: plato.precio, cantidad: 1 })
                  }
                >
                  <b>{plato.nombre}</b>
                  <small className="num">{plata(plato.precio)}</small>
                  {plato.tipo === 'especial' && <span className="marca-especial">Especial</span>}
                  {lleva && <span className="insignia num">{formatoCantidad(lleva)}</span>}
                </button>
              )
            })}
            {menu.productos.map((producto) => {
              const lleva = yaElegido.get(`producto-${producto.id}`)
              return (
                <button
                  key={`producto-${producto.id}`}
                  className={`tarjeta-item ${lleva ? 'elegido' : ''}`}
                  aria-pressed={Boolean(lleva)}
                  onClick={() =>
                    anotar({
                      producto_id: producto.id,
                      nombre: producto.nombre,
                      precio: producto.precio_de_venta,
                      cantidad: 1,
                    })
                  }
                >
                  <b>{producto.nombre}</b>
                  <small className="num">{plata(producto.precio_de_venta)}</small>
                  {lleva && <span className="insignia num">{formatoCantidad(lleva)}</span>}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* ------------------------------------------- nota para la cocina */}
      {conNota && (
        <NotaDelPlato
          nombre={conNota.nombre}
          cantidad={conNota.cantidad}
          notaActual={conNota.notas}
          alGuardar={(nota, soloUno) => guardarNota(conNota, nota, soloUno)}
          cancelar={() => setConNota(null)}
        />
      )}

      {/* ---------------------------------------- corregir algo ya enviado */}
      {corrigiendo && pedido && (
        <CorregirItem
          pedidoId={pedido.id}
          detalle={corrigiendo}
          // Si lo envió otra persona, ya se sabe que hará falta el código.
          pideCodigo={
            sesion?.rol !== 'administrador' && corrigiendo.agregado_por_id !== sesion?.id
          }
          alTerminar={(actualizado) => {
            setPedido(actualizado)
            setCorrigiendo(null)
            setListo('Corregido. La caja ya tiene la cuenta nueva.')
          }}
          cancelar={() => setCorrigiendo(null)}
        />
      )}

      {/* ------------------------------------------- confirmar el pedido */}
      {confirmando && (
        <div className="velo" role="dialog" aria-modal="true" aria-labelledby="titulo-confirmar">
          <div className="confirmacion">
            <h2 id="titulo-confirmar" className="confirmacion-titulo">
              Confirmar pedido
            </h2>
            <p className="confirmacion-nota">
              Esto es lo que va a subir a la mesa {numero}
              {!ocupada && enEspera.length === 0 && '. La mesa queda ocupada'}.
            </p>

            <div className="confirmacion-lista">
              {borrador.map((linea) => (
                <div key={linea.clave} className="confirmacion-linea">
                  <span className="confirmacion-cantidad num">{formatoCantidad(linea.cantidad)}</span>
                  <span className="confirmacion-nombre">
                    {linea.nombre}
                    {linea.notas && <small className="nota-plato">{linea.notas}</small>}
                  </span>
                  <span className="confirmacion-precio num">
                    {plata(linea.precio * linea.cantidad)}
                  </span>
                </div>
              ))}
            </div>

            <div className="confirmacion-total">
              <span className="etiqueta">Total por enviar</span>
              <span className="num">{plata(totalBorrador)}</span>
            </div>

            <div className="confirmacion-botones">
              <button
                className="btn-secundario"
                onClick={() => setConfirmando(false)}
                disabled={subiendo}
              >
                Corregir pedido
              </button>
              <button className="btn-primario" onClick={() => void confirmar()} disabled={subiendo}>
                {subiendo ? 'Enviando…' : 'Confirmar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------- la cuenta */}
      {viendoCuenta && pedido && (
        <div className="velo" role="dialog" aria-modal="true" aria-labelledby="titulo-cuenta">
          <div className="confirmacion">
            <h2 id="titulo-cuenta" className="confirmacion-titulo">
              Cuenta de la mesa {numero}
            </h2>

            <div className="confirmacion-lista">
              {pedido.detalles.map((detalle) => (
                <div key={detalle.id} className="confirmacion-linea">
                  <span className="confirmacion-cantidad num">
                    {formatoCantidad(detalle.cantidad)}
                  </span>
                  <span className="confirmacion-nombre">{detalle.nombre}</span>
                  <span className="confirmacion-precio num">{plata(detalle.subtotal)}</span>
                </div>
              ))}
            </div>

            <div className="cuenta-total">
              <span className="etiqueta">Total a pagar</span>
              <span className="cuenta-cifra num">{plata(pedido.total)}</span>
            </div>

            {enEspera.length > 0 && (
              <p className="aviso aviso-atencion">
                Ojo: hay {plata(totalEnEspera)} de esta mesa que todavía no llegan a la caja
                por falta de señal. No están en esta cuenta.
              </p>
            )}

            {borrador.length > 0 && (
              <p className="aviso aviso-atencion">
                Ojo: tienes {borrador.length}{' '}
                {borrador.length === 1 ? 'cosa anotada' : 'cosas anotadas'} sin enviar por{' '}
                {plata(totalBorrador)}. No están en esta cuenta.
              </p>
            )}

            <button className="btn-primario" onClick={() => setViendoCuenta(false)}>
              Listo
            </button>
          </div>
        </div>
      )}

      <footer className="celular-pie">
        <button className="btn-secundario" onClick={() => setEligiendo((v) => !v)}>
          {eligiendo ? 'Ocultar el menú' : 'Agregar algo más'}
        </button>

        {borrador.length > 0 ? (
          <button className="btn-primario" onClick={() => setConfirmando(true)}>
            SUBIR PEDIDO · {plata(totalBorrador)}
          </button>
        ) : (
          <button
            className="btn-primario"
            onClick={() => void verCuenta()}
            disabled={subiendo || !ocupada}
          >
            {pedido?.estado === 'cuenta_pedida' ? 'VER LA CUENTA' : 'PEDIR LA CUENTA'}
          </button>
        )}
      </footer>
    </div>
  )
}
