import { useState, type FormEvent } from 'react'

import { api } from '../api/cliente'
import type { TurnoCaja } from '../api/tipos'
import { leerPesos, plata } from '../formato'
import Fondo from './Fondo'

/** Pantalla que aparece cuando todavía no hay turno abierto. */
export function AbrirCaja({ alAbrir }: { alAbrir: (turno: TurnoCaja) => void }) {
  const [base, setBase] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [abriendo, setAbriendo] = useState(false)

  const enPesos = leerPesos(base)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    if (enPesos === null) {
      setError('Escribe con cuánto empiezas. Si no hay base, escribe 0.')
      return
    }
    setAbriendo(true)
    setError(null)
    try {
      alAbrir(await api.post<TurnoCaja>('/caja/abrir', { base_inicial: enPesos }))
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo abrir la caja.')
      setAbriendo(false)
    }
  }

  return (
    <div className="centrado">
      <Fondo />
      <form className="turno-panel" onSubmit={enviar}>
        <h2>Abrir la caja</h2>
        <p className="pista">
          Cuenta la plata con la que empiezas y escríbela aquí. Al cerrar, el sistema
          la usa para saber si el cajón cuadra.
        </p>

        <label className="campo">
          <span className="etiqueta">Con cuánto empiezas</span>
          <input
            value={base}
            onChange={(e) => setBase(e.target.value)}
            inputMode="numeric"
            placeholder="0"
            autoFocus
          />
        </label>
        {enPesos !== null && (
          <span className="lectura-plata">
            Empiezas con <b className="num">{plata(enPesos)}</b>
          </span>
        )}

        {error && <p className="aviso aviso-error">{error}</p>}

        <button className="btn-primario" type="submit" disabled={abriendo}>
          {abriendo ? 'ABRIENDO…' : 'ABRIR LA CAJA'}
        </button>
      </form>
    </div>
  )
}

/** Cuadre del final del turno. */
export function CerrarCaja({
  alCerrar,
  cancelar,
}: {
  alCerrar: () => void
  cancelar: () => void
}) {
  const [contado, setContado] = useState('')
  const [resultado, setResultado] = useState<TurnoCaja | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cerrando, setCerrando] = useState(false)

  const enPesos = leerPesos(contado)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    // Un campo vacío no es "conté cero": el cierre no se puede deshacer, y
    // cerrar sin contar dejaría registrado un faltante de todo el turno.
    if (enPesos === null) {
      setError('Escribe cuánto contaste. Si el cajón está vacío, escribe 0.')
      return
    }
    setCerrando(true)
    setError(null)
    try {
      setResultado(await api.post<TurnoCaja>('/caja/cerrar', { efectivo_contado: enPesos }))
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cerrar la caja.')
    } finally {
      setCerrando(false)
    }
  }

  if (resultado) {
    const diferencia = resultado.diferencia ?? 0
    const cuadra = diferencia === 0
    return (
      <div className="turno-fondo">
        <div className="turno-panel">
          <h2>Caja cerrada</h2>
          <div className="turno-fila">
            <span>Debería haber</span>
            <span className="num">{plata(resultado.efectivo_esperado ?? 0)}</span>
          </div>
          <div className="turno-fila">
            <span>Contaste</span>
            <span className="num">{plata(resultado.efectivo_contado ?? 0)}</span>
          </div>
          <p className={`aviso ${cuadra ? 'aviso-ok' : 'aviso-atencion'}`}>
            {cuadra
              ? 'El cajón cuadra exacto.'
              : diferencia > 0
                ? `Sobran ${plata(diferencia)}.`
                : `Faltan ${plata(Math.abs(diferencia))}.`}
          </p>
          <button className="btn-primario" onClick={alCerrar}>
            LISTO
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="turno-fondo">
      <form className="turno-panel" onSubmit={enviar}>
        <h2>Cerrar la caja</h2>
        <p className="pista">
          Cuenta el efectivo del cajón y escribe cuánto hay. El sistema no te muestra
          antes cuánto debería haber: así el conteo es de verdad.
        </p>

        <label className="campo">
          <span className="etiqueta">Efectivo contado</span>
          <input
            value={contado}
            onChange={(e) => setContado(e.target.value)}
            inputMode="numeric"
            placeholder="0"
            autoFocus
          />
        </label>
        {/* El cierre no se puede deshacer: se muestra la cifra como la
            entendió el sistema para que un punto de más no cueste caro. */}
        {enPesos !== null && (
          <span className="lectura-plata">
            Vas a registrar <b className="num">{plata(enPesos)}</b> en el cajón
          </span>
        )}

        {error && <p className="aviso aviso-error">{error}</p>}

        <button className="btn-primario" type="submit" disabled={cerrando}>
          {cerrando ? 'CERRANDO…' : 'CERRAR Y CUADRAR'}
        </button>
        <button className="btn-secundario" type="button" onClick={cancelar}>
          Todavía no
        </button>
      </form>
    </div>
  )
}
