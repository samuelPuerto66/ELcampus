import { useEffect, useRef, useState } from 'react'

import { api } from '../api/cliente'
import type { ClienteFiado, MetodoPago } from '../api/tipos'
import { leerPesos, plata } from '../formato'

/**
 * El lado derecho de la caja: cuánto se cobra y cómo se paga.
 *
 * Aquí viven el método de pago, el pago dividido, el descuento, la
 * propina y el fiado. Lo que se vende (lo escaneado o la mesa) lo maneja
 * Caja.tsx; este panel solo recibe el subtotal y, al cobrar, le devuelve a
 * la caja un `Cobro` listo para mandar al servidor.
 *
 * Después de cada venta la caja lo vuelve a montar desde cero (con `key`),
 * así que nunca queda un descuento o un pago dividido de la venta anterior.
 */

/** Cómo se pagó, tal como lo espera el servidor. */
export interface Cobro {
  metodo_pago?: MetodoPago
  pagos?: { metodo: MetodoPago; monto: number }[]
  descuento: number
  motivo_descuento: string | null
  codigo_autorizacion: string | null
  propina: number
  cliente_fiado_id: number | null
}

export const METODOS: { valor: MetodoPago; texto: string }[] = [
  { valor: 'efectivo', texto: 'Efectivo' },
  { valor: 'nequi', texto: 'Nequi' },
  { valor: 'daviplata', texto: 'Daviplata' },
  { valor: 'tarjeta', texto: 'Tarjeta' },
  { valor: 'fiado', texto: 'Fiado' },
]

export const nombreDelMetodo = (metodo: string) =>
  METODOS.find((m) => m.valor === metodo)?.texto ?? 'Pago dividido'

/** Hasta cuánto rebaja el vendedor sin pedir el código. El servidor tiene
 *  la misma regla y es el que manda; esto es solo para avisar antes. */
const DESCUENTO_LIBRE = 0.1

/** En Colombia la propina sugerida es el 10%, y por ley es voluntaria:
 *  se le pregunta al cliente, nunca se mete sola en la cuenta. */
const PROPINA_SUGERIDA = 0.1

type ModoPropina = 'ninguna' | 'sugerida' | 'otra'

export default function PanelCobro({
  subtotal,
  esMesa,
  hayAlgo,
  cobrando,
  esAdmin,
  alCobrar,
}: {
  /** Lo que suman los productos, antes de descuento y propina. */
  subtotal: number
  /** La propina solo se ofrece al cobrar una mesa. */
  esMesa: boolean
  hayAlgo: boolean
  cobrando: boolean
  /** Un administrador no necesita código para descontar. */
  esAdmin: boolean
  alCobrar: (cobro: Cobro) => void
}) {
  const [metodoPago, setMetodoPago] = useState<MetodoPago>('efectivo')
  const [dividido, setDividido] = useState(false)
  const [montos, setMontos] = useState<Partial<Record<MetodoPago, string>>>({})
  const [recibido, setRecibido] = useState('')
  const [conDescuento, setConDescuento] = useState(false)
  const [descuentoTexto, setDescuentoTexto] = useState('')
  const [motivoDescuento, setMotivoDescuento] = useState('')
  const [codigoAdmin, setCodigoAdmin] = useState('')
  const [modoPropina, setModoPropina] = useState<ModoPropina>('ninguna')
  const [propinaTexto, setPropinaTexto] = useState('')
  const [clientesFiado, setClientesFiado] = useState<ClienteFiado[] | null>(null)
  const [clienteFiadoId, setClienteFiadoId] = useState<number | null>(null)

  // ------------------------------------------------------- las cuentas
  const descuentoEscrito = conDescuento ? (leerPesos(descuentoTexto) ?? 0) : 0
  const descuentoExcede = descuentoEscrito > subtotal
  const descuento = Math.min(descuentoEscrito, subtotal)
  const total = subtotal - descuento

  const propinaSugerida = Math.round((total * PROPINA_SUGERIDA) / 100) * 100
  const propina = !esMesa
    ? 0
    : modoPropina === 'sugerida'
      ? propinaSugerida
      : modoPropina === 'otra'
        ? (leerPesos(propinaTexto) ?? 0)
        : 0
  const aCobrar = total + propina

  const montoDividido = (metodo: MetodoPago) => leerPesos(montos[metodo] ?? '') ?? 0
  const pagosDivididos = METODOS.map((m) => ({
    metodo: m.valor,
    monto: montoDividido(m.valor),
  })).filter((p) => p.monto > 0)
  const falta = aCobrar - pagosDivididos.reduce((suma, p) => suma + p.monto, 0)

  /** Cuánto de lo cobrado va por un método: todo, si no está dividido. */
  const montoPor = (metodo: MetodoPago) =>
    dividido ? montoDividido(metodo) : metodoPago === metodo ? aCobrar : 0

  // Lo que va al cajón: con el pago dividido, solo la parte en efectivo.
  const enEfectivo = montoPor('efectivo')
  const recibidoEnPesos = leerPesos(recibido)
  const vuelto = recibidoEnPesos !== null && enEfectivo > 0 ? recibidoEnPesos - enEfectivo : null

  const necesitaCodigo = descuento > subtotal * DESCUENTO_LIBRE && !esAdmin

  // --------------------------------------------------------- el fiado
  const montoFiado = montoPor('fiado')
  const clienteFiado = clientesFiado?.find((c) => c.id === clienteFiadoId) ?? null
  const cupoLibre =
    clienteFiado && clienteFiado.cupo !== null ? clienteFiado.cupo - clienteFiado.saldo : null

  // La lista se pide solo cuando hace falta: casi ninguna venta es fiada.
  useEffect(() => {
    if (montoFiado > 0 && clientesFiado === null) {
      api
        .get<ClienteFiado[]>('/fiado/clientes')
        .then(setClientesFiado)
        .catch(() => setClientesFiado([]))
    }
  }, [montoFiado, clientesFiado])

  // Por qué todavía no se puede cobrar, en palabras. Un botón apagado sin
  // explicación hace que el cajero lo presione diez veces.
  const falla: string | null = !hayAlgo
    ? null
    : descuentoExcede
      ? 'El descuento es mayor que la cuenta.'
      : descuento > 0 && !motivoDescuento.trim()
        ? 'Escribe el motivo del descuento.'
        : necesitaCodigo && !codigoAdmin.trim()
          ? 'Falta el código del administrador para el descuento.'
          : dividido && aCobrar > 0 && falta !== 0
            ? falta > 0
              ? `Faltan ${plata(falta)} por repartir entre los pagos.`
              : `Los pagos se pasan por ${plata(-falta)}.`
            : montoFiado > 0 && !clienteFiado
              ? 'Escoge a quién se le fía.'
              : cupoLibre !== null && montoFiado > cupoLibre
                ? `A ${clienteFiado!.nombre} solo le quedan ${plata(Math.max(0, cupoLibre))} de cupo.`
                : null
  const sePuedeCobrar = hayAlgo && !cobrando && falla === null

  // ------------------------------------------------------------ cobrar
  function cobrar() {
    if (!sePuedeCobrar) return
    alCobrar({
      ...(dividido && aCobrar > 0 ? { pagos: pagosDivididos } : { metodo_pago: metodoPago }),
      descuento,
      motivo_descuento: descuento > 0 ? motivoDescuento.trim() : null,
      codigo_autorizacion: necesitaCodigo ? codigoAdmin.trim() : null,
      propina,
      cliente_fiado_id: montoFiado > 0 ? clienteFiadoId : null,
    })
  }

  // F12 cobra sin soltar el lector ni tocar el mouse.
  const cobrarConTecla = useRef(cobrar)
  cobrarConTecla.current = cobrar
  useEffect(() => {
    const atajo = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'F12') {
        e.preventDefault()
        cobrarConTecla.current()
      }
    }
    window.addEventListener('keydown', atajo)
    return () => window.removeEventListener('keydown', atajo)
  }, [])

  /** Llena un método con lo que falta, para no hacer la resta a mano. */
  function ponerElResto(metodo: MetodoPago) {
    const resto = montoDividido(metodo) + falta
    setMontos((m) => ({ ...m, [metodo]: resto.toLocaleString('es-CO') }))
  }

  return (
    <>
      <div className="total-caja">
        <span className="etiqueta">{descuento || propina ? 'A cobrar' : 'Total'}</span>
        <span className="total-valor num">{plata(aCobrar)}</span>
        {(descuento > 0 || propina > 0) && (
          <span className="desglose num">
            {plata(subtotal)}
            {descuento > 0 && ` − ${plata(descuento)} de descuento`}
            {propina > 0 && ` + ${plata(propina)} de propina`}
          </span>
        )}
      </div>

      {/* ------------------------------------------ propina (solo mesas) */}
      {esMesa && (
        <div className="opcion-cobro">
          <span className="etiqueta">Propina voluntaria · pregúntale al cliente</span>
          <div className="pagos tres">
            <button
              className={`pago ${modoPropina === 'ninguna' ? 'activo' : ''}`}
              onClick={() => setModoPropina('ninguna')}
            >
              Sin propina
            </button>
            <button
              className={`pago ${modoPropina === 'sugerida' ? 'activo' : ''}`}
              onClick={() => setModoPropina('sugerida')}
            >
              10% · {plata(propinaSugerida)}
            </button>
            <button
              className={`pago ${modoPropina === 'otra' ? 'activo' : ''}`}
              onClick={() => setModoPropina('otra')}
              data-conserva-foco
            >
              Otro valor
            </button>
          </div>
          {modoPropina === 'otra' && (
            <input
              className="campo-cobro num"
              value={propinaTexto}
              onChange={(e) => setPropinaTexto(e.target.value)}
              placeholder="¿Cuánto dejó?"
              inputMode="numeric"
              autoFocus
            />
          )}
        </div>
      )}

      {/* ------------------------------------------ descuento */}
      {hayAlgo &&
        (conDescuento ? (
          <div className="opcion-cobro">
            <div className="opcion-cabeza">
              <span className="etiqueta">Descuento o cortesía</span>
              <button
                className="btn-peligro"
                onClick={() => {
                  setConDescuento(false)
                  setDescuentoTexto('')
                  setMotivoDescuento('')
                  setCodigoAdmin('')
                }}
              >
                Quitar
              </button>
            </div>
            <div className="opcion-fila">
              <input
                className="campo-cobro num"
                value={descuentoTexto}
                onChange={(e) => setDescuentoTexto(e.target.value)}
                placeholder="¿Cuánto se rebaja?"
                inputMode="numeric"
                autoFocus
              />
              <button
                className="btn-secundario btn-angosto"
                onClick={() => setDescuentoTexto(String(subtotal))}
              >
                Todo gratis
              </button>
            </div>
            <input
              className="campo-cobro"
              value={motivoDescuento}
              onChange={(e) => setMotivoDescuento(e.target.value)}
              placeholder="¿Por qué? Ej: cliente frecuente, la casa invita"
            />
            {necesitaCodigo && (
              <>
                <span className="pista">
                  Es más del 10% de la cuenta: un administrador tiene que escribir su código.
                </span>
                <input
                  className="campo-cobro"
                  type="password"
                  value={codigoAdmin}
                  onChange={(e) => setCodigoAdmin(e.target.value)}
                  placeholder="Código de administrador"
                  autoComplete="off"
                />
              </>
            )}
          </div>
        ) : (
          <button className="btn-enlace" onClick={() => setConDescuento(true)} data-conserva-foco>
            + Descuento o cortesía
          </button>
        ))}

      {/* ------------------------------------------ cómo paga */}
      {aCobrar > 0 && (
        <>
          {!dividido && (
            <div className="pagos">
              {METODOS.map((m) => (
                <button
                  key={m.valor}
                  className={`pago ${metodoPago === m.valor ? 'activo' : ''} ${
                    m.valor === 'fiado' ? 'ancho' : ''
                  }`}
                  onClick={() => setMetodoPago(m.valor)}
                >
                  {m.texto}
                </button>
              ))}
            </div>
          )}

          {dividido && (
            <div className="vuelto division">
              {METODOS.map((m) => (
                <label key={m.valor} className="fila">
                  <span>{m.texto}</span>
                  <span className="division-campo">
                    {falta > 0 && (
                      <button
                        type="button"
                        className="btn-resto"
                        onClick={(e) => {
                          e.preventDefault()
                          ponerElResto(m.valor)
                        }}
                      >
                        el resto
                      </button>
                    )}
                    <input
                      className="campo-recibido num"
                      value={montos[m.valor] ?? ''}
                      onChange={(e) =>
                        setMontos((actual) => ({ ...actual, [m.valor]: e.target.value }))
                      }
                      placeholder="0"
                      inputMode="numeric"
                    />
                  </span>
                </label>
              ))}
              <div className={`fila destacada ${falta === 0 ? '' : 'pendiente'}`}>
                {falta === 0 ? (
                  <span>✓ Cuadra con la cuenta</span>
                ) : (
                  <>
                    <span>{falta > 0 ? 'Falta' : 'Se pasa por'}</span>
                    <span className="num">{plata(Math.abs(falta))}</span>
                  </>
                )}
              </div>
            </div>
          )}

          <button
            className="btn-enlace"
            onClick={() => {
              setDividido((d) => !d)
              setMontos({})
            }}
            data-conserva-foco
          >
            {dividido
              ? 'Pagar todo por un solo lado'
              : '+ Dividir el pago (ej. mitad efectivo, mitad Nequi)'}
          </button>

          {/* ---------------------------------------- a quién se le fía */}
          {montoFiado > 0 && (
            <div className="opcion-cobro">
              <span className="etiqueta">¿A quién se le fía?</span>
              {clientesFiado === null ? (
                <span className="pista">Cargando los clientes…</span>
              ) : clientesFiado.length === 0 ? (
                <span className="pista">
                  No hay clientes de fiado. El administrador los registra en la pestaña Fiado.
                </span>
              ) : (
                <select
                  className="campo-cobro"
                  value={clienteFiadoId ?? ''}
                  onChange={(e) => setClienteFiadoId(Number(e.target.value) || null)}
                >
                  <option value="">Escoge el cliente…</option>
                  {clientesFiado.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nombre}
                      {c.saldo > 0 ? ` · debe ${plata(c.saldo)}` : ''}
                    </option>
                  ))}
                </select>
              )}
              {clienteFiado && (
                <span className="pista">
                  {cupoLibre === null
                    ? 'Sin límite de cupo.'
                    : `Le quedan ${plata(Math.max(0, cupoLibre))} de cupo.`}
                </span>
              )}
            </div>
          )}

          {enEfectivo > 0 && (
            <div className="vuelto">
              <label className="fila">
                <span>{dividido ? 'Le entregan en efectivo' : 'Recibido'}</span>
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
              {vuelto !== null && vuelto < 0 && (
                <div className="fila destacada pendiente">
                  <span>Le faltan</span>
                  <span className="num">{plata(-vuelto)}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}

      <button className="btn-cobrar" onClick={cobrar} disabled={!sePuedeCobrar}>
        {aCobrar === 0 && hayAlgo ? 'REGISTRAR CORTESÍA' : 'COBRAR'} <small>F12</small>
      </button>
      {falla && <span className="por-que-no">{falla}</span>}
    </>
  )
}
