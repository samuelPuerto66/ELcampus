import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/cliente'
import type { ClienteFiado, CuentaFiado, MetodoPago } from '../api/tipos'
import { hora, leerPesos, plata } from '../formato'

/**
 * El cuaderno de fiados: a quién se le fía, cuánto debe y sus abonos.
 *
 * Lo usan dos pantallas:
 * - La caja (botón "Fiados"), donde llega la gente a pagar: ve las cuentas
 *   y recibe abonos.
 * - El administrador (pestaña "Fiado"), que además registra clientes,
 *   les pone cupo, deja de fiarles y anula abonos mal registrados.
 *
 * Vender fiado no se hace aquí: se cobra en la caja con "Fiado" como forma
 * de pago.
 */
export default function Fiados({ esAdmin }: { esAdmin: boolean }) {
  const [clientes, setClientes] = useState<ClienteFiado[] | null>(null)
  const [buscar, setBuscar] = useState('')
  const [verInactivos, setVerInactivos] = useState(false)
  const [elegido, setElegido] = useState<number | null>(null)
  const [creando, setCreando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setClientes(
        await api.get<ClienteFiado[]>(
          `/fiado/clientes${verInactivos ? '?incluir_inactivos=true' : ''}`,
        ),
      )
      setError(null)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar el fiado.')
    }
  }, [verInactivos])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (!clientes) return <p className="cargando">{error ?? 'Cargando el fiado…'}</p>

  const texto = buscar.trim().toLowerCase()
  const visibles = clientes.filter(
    (c) => !texto || c.nombre.toLowerCase().includes(texto) || c.telefono?.includes(texto),
  )
  const deudores = clientes.filter((c) => c.saldo > 0)
  const teDeben = deudores.reduce((suma, c) => suma + c.saldo, 0)

  return (
    <div className="fiados">
      <section className="fiados-lista">
        <p className="fiados-total">
          Te deben <b className="num">{plata(teDeben)}</b>
          {deudores.length > 0 &&
            ` entre ${deudores.length} ${deudores.length === 1 ? 'cliente' : 'clientes'}`}
        </p>

        <div className="opcion-fila">
          <input
            className="campo-cobro"
            value={buscar}
            onChange={(e) => setBuscar(e.target.value)}
            placeholder="Buscar por nombre o teléfono"
          />
          {esAdmin && (
            <button className="btn-secundario btn-angosto" onClick={() => setCreando(true)}>
              + Nuevo
            </button>
          )}
        </div>

        {esAdmin && (
          <label className="casilla">
            <input
              type="checkbox"
              checked={verInactivos}
              onChange={(e) => setVerInactivos(e.target.checked)}
            />
            <span>Ver también a los que ya no se les fía</span>
          </label>
        )}

        {error && <p className="aviso aviso-error">{error}</p>}

        {creando && (
          <NuevoCliente
            alCrear={(nuevo) => {
              setCreando(false)
              setElegido(nuevo.id)
              void cargar()
            }}
            cancelar={() => setCreando(false)}
          />
        )}

        {visibles.length === 0 && (
          <p className="pista">
            {clientes.length === 0
              ? esAdmin
                ? 'Todavía no hay a quién fiarle. Registra al primero con «+ Nuevo».'
                : 'Todavía no hay a quién fiarle. Los clientes los registra el administrador.'
              : 'Nadie coincide con esa búsqueda.'}
          </p>
        )}

        {visibles.map((c) => (
          <button
            key={c.id}
            className={`fila-fiado ${elegido === c.id ? 'elegido' : ''} ${c.activo ? '' : 'apagado'}`}
            onClick={() => setElegido(c.id)}
          >
            <span className="fila-fiado-nombre">
              {c.nombre}
              <small>
                {c.telefono ?? 'sin teléfono'}
                {!c.activo && ' · ya no se le fía'}
              </small>
            </span>
            <span className={`num ${c.saldo > 0 ? 'debe' : 'al-dia'}`}>
              {c.saldo > 0 ? plata(c.saldo) : 'al día'}
            </span>
          </button>
        ))}
      </section>

      <section className="fiados-cuenta">
        {elegido === null ? (
          <p className="pista">Escoge un cliente para ver su cuenta o recibirle un abono.</p>
        ) : (
          <CuentaDeCliente
            key={elegido}
            clienteId={elegido}
            esAdmin={esAdmin}
            alCambiar={() => void cargar()}
          />
        )}
      </section>
    </div>
  )
}

/** Registrar a alguien en el cuaderno. Solo el administrador. */
function NuevoCliente({
  alCrear,
  cancelar,
}: {
  alCrear: (cliente: ClienteFiado) => void
  cancelar: () => void
}) {
  const [nombre, setNombre] = useState('')
  const [telefono, setTelefono] = useState('')
  const [cupo, setCupo] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function crear(e: FormEvent) {
    e.preventDefault()
    try {
      alCrear(
        await api.post<ClienteFiado>('/fiado/clientes', {
          nombre,
          telefono: telefono || null,
          cupo: leerPesos(cupo),
        }),
      )
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo registrar.')
    }
  }

  return (
    <form className="opcion-cobro" onSubmit={crear}>
      <span className="etiqueta">Nuevo cliente de fiado</span>
      <input value={nombre} onChange={(e) => setNombre(e.target.value)} placeholder="Nombre" autoFocus />
      <input
        value={telefono}
        onChange={(e) => setTelefono(e.target.value)}
        placeholder="Teléfono (opcional)"
        inputMode="tel"
      />
      <input
        className="num"
        value={cupo}
        onChange={(e) => setCupo(e.target.value)}
        placeholder="Cupo: hasta cuánto puede deber"
        inputMode="numeric"
      />
      <span className="pista">
        {leerPesos(cupo) !== null
          ? `Se le puede fiar hasta ${plata(leerPesos(cupo) ?? 0)}.`
          : 'Sin cupo, no hay límite. Lo prudente es ponerle uno.'}
      </span>
      {error && <p className="aviso aviso-error">{error}</p>}
      <div className="opcion-fila">
        <button className="btn-secundario btn-angosto" type="button" onClick={cancelar}>
          Cancelar
        </button>
        <button className="btn-primario btn-angosto" type="submit">
          Registrar
        </button>
      </div>
    </form>
  )
}

const METODOS_DE_ABONO: { valor: MetodoPago; texto: string }[] = [
  { valor: 'efectivo', texto: 'Efectivo' },
  { valor: 'nequi', texto: 'Nequi' },
  { valor: 'daviplata', texto: 'Daviplata' },
  { valor: 'tarjeta', texto: 'Tarjeta' },
]

const fecha = (iso: string) =>
  `${new Date(iso).toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })} · ${hora(iso)}`

/** La cuenta de un cliente: lo que debe, sus movimientos y los abonos. */
function CuentaDeCliente({
  clienteId,
  esAdmin,
  alCambiar,
}: {
  clienteId: number
  esAdmin: boolean
  alCambiar: () => void
}) {
  const [cuenta, setCuenta] = useState<CuentaFiado | null>(null)
  const [monto, setMonto] = useState('')
  const [metodo, setMetodo] = useState<MetodoPago>('efectivo')
  const [cupo, setCupo] = useState('')
  const [aviso, setAviso] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const leida = await api.get<CuentaFiado>(`/fiado/clientes/${clienteId}`)
      setCuenta(leida)
      setCupo(leida.cupo === null ? '' : String(leida.cupo))
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cargar la cuenta.')
    }
  }, [clienteId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  /** Después de cualquier cambio: se recarga la cuenta y la lista. */
  async function hecho(mensaje: string) {
    setAviso(mensaje)
    setError(null)
    await cargar()
    alCambiar()
  }

  async function abonar(e: FormEvent) {
    e.preventDefault()
    const pesos = leerPesos(monto)
    if (!pesos) {
      setError('Escribe cuánto trajo.')
      return
    }
    try {
      await api.post(`/fiado/clientes/${clienteId}/abonos`, { monto: pesos, metodo })
      setMonto('')
      await hecho(`Abono de ${plata(pesos)} registrado.`)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo registrar el abono.')
    }
  }

  async function editar(cambios: Partial<Pick<ClienteFiado, 'cupo' | 'activo'>>, mensaje: string) {
    try {
      await api.patch(`/fiado/clientes/${clienteId}`, cambios)
      await hecho(mensaje)
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar.')
    }
  }

  async function anularAbono(abonoId: number, valor: number) {
    const motivo = window.prompt(`Vas a anular un abono de ${plata(valor)}.\n\n¿Por qué?`)
    if (!motivo?.trim()) return
    try {
      await api.post(`/fiado/abonos/${abonoId}/anular`, { motivo: motivo.trim() })
      await hecho('Abono anulado: la deuda volvió a subir.')
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo anular.')
    }
  }

  if (!cuenta) return <p className="pista">{error ?? 'Cargando la cuenta…'}</p>

  const pesosDelAbono = leerPesos(monto)

  return (
    <div className="cuenta-fiado">
      <div className="cuenta-fiado-cabeza">
        <span>
          <b>{cuenta.nombre}</b>
          <small>{cuenta.telefono ?? 'sin teléfono'}</small>
        </span>
        <span className="cuenta-fiado-saldo">
          <span className="etiqueta">Debe</span>
          <b className={`num ${cuenta.saldo > 0 ? 'debe' : 'al-dia'}`}>{plata(cuenta.saldo)}</b>
          <small>
            {cuenta.cupo === null ? 'sin límite de cupo' : `cupo de ${plata(cuenta.cupo)}`}
          </small>
        </span>
      </div>

      {aviso && <p className="aviso aviso-ok">{aviso}</p>}
      {error && <p className="aviso aviso-error">{error}</p>}

      {/* ------------------------------------------------ recibir un abono */}
      {cuenta.saldo > 0 && (
        <form className="opcion-cobro" onSubmit={abonar}>
          <span className="etiqueta">Recibir un abono</span>
          <div className="opcion-fila">
            <input
              className="campo-cobro num"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
              placeholder="¿Cuánto trajo?"
              inputMode="numeric"
            />
            <button
              type="button"
              className="btn-secundario btn-angosto"
              onClick={() => setMonto(String(cuenta.saldo))}
            >
              Todo
            </button>
          </div>
          <div className="pagos">
            {METODOS_DE_ABONO.map((m) => (
              <button
                key={m.valor}
                type="button"
                className={`pago ${metodo === m.valor ? 'activo' : ''}`}
                onClick={() => setMetodo(m.valor)}
              >
                {m.texto}
              </button>
            ))}
          </div>
          <button className="btn-primario" type="submit" disabled={!pesosDelAbono}>
            {pesosDelAbono ? `REGISTRAR ABONO DE ${plata(pesosDelAbono)}` : 'REGISTRAR ABONO'}
          </button>
        </form>
      )}

      {/* --------------------------------------- lo que decide el dueño */}
      {esAdmin && (
        <div className="opcion-cobro">
          <span className="etiqueta">Cupo y estado</span>
          <div className="opcion-fila">
            <input
              className="campo-cobro num"
              value={cupo}
              onChange={(e) => setCupo(e.target.value)}
              placeholder="Sin límite"
              inputMode="numeric"
            />
            <button
              className="btn-secundario btn-angosto"
              onClick={() =>
                void editar(
                  { cupo: leerPesos(cupo) },
                  leerPesos(cupo) === null
                    ? 'Quedó sin límite de cupo.'
                    : `Cupo cambiado a ${plata(leerPesos(cupo) ?? 0)}.`,
                )
              }
            >
              Guardar cupo
            </button>
          </div>
          <button
            className={cuenta.activo ? 'btn-peligro' : 'btn-enlace'}
            onClick={() =>
              void editar(
                { activo: !cuenta.activo },
                cuenta.activo
                  ? `A ${cuenta.nombre} ya no se le fía. Lo que debe sigue anotado.`
                  : `A ${cuenta.nombre} se le vuelve a fiar.`,
              )
            }
          >
            {cuenta.activo ? 'Dejar de fiarle' : 'Volver a fiarle'}
          </button>
        </div>
      )}

      {/* ------------------------------------------------ los movimientos */}
      <div className="bloque">
        <span className="etiqueta">Movimientos</span>
        {cuenta.movimientos.length === 0 && <p className="pista">Todavía no hay nada anotado.</p>}
        {cuenta.movimientos.map((m) => (
          <div
            key={`${m.tipo}-${m.id}`}
            className={`movimiento ${m.tipo} ${m.anulado ? 'anulado' : ''}`}
          >
            <span className="movimiento-texto">
              {m.tipo === 'fiado' ? `Se llevó fiado · venta #${m.id}` : 'Abonó'}
              <small>
                {fecha(m.fecha)} · {m.detalle}
                {m.anulado && ' · ANULADO'}
              </small>
            </span>
            <span className="movimiento-monto num">
              {m.tipo === 'fiado' ? '+' : '−'}
              {plata(m.monto)}
            </span>
            {esAdmin && m.tipo === 'abono' && !m.anulado && (
              <button className="btn-peligro" onClick={() => void anularAbono(m.id, m.monto)}>
                Anular
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
