import { useState } from 'react'

import { api, ErrorApi } from '../api/cliente'
import type { DetallePedido, Pedido } from '../api/tipos'
import { cantidad as formatoCantidad, plata } from '../formato'

/** Las razones de siempre, para no tener que escribirlas con el celular en
 *  una mano. Igual se puede escribir otra. */
const MOTIVOS = ['Se anotó de más', 'El cliente cambió de idea', 'Era de otra mesa', 'Se acabó']

/**
 * Quitar de una mesa algo que ya se había enviado.
 *
 * Las reglas las pone el servidor: lo propio y recién enviado se corrige
 * solo; lo demás necesita el código de un administrador. Esta pantalla pide
 * el código de una vez cuando es obvio que hará falta (`pideCodigo`), y si
 * el servidor lo pide en otro caso, muestra el campo en ese momento.
 *
 * La usan el celular del mesero y la caja.
 */
export default function CorregirItem({
  pedidoId,
  detalle,
  pideCodigo,
  alTerminar,
  cancelar,
}: {
  pedidoId: number
  detalle: DetallePedido
  pideCodigo: boolean
  alTerminar: (pedido: Pedido) => void
  cancelar: () => void
}) {
  // Lo que va por kilos se quita completo: andar restando gramos de una
  // morraja no tiene sentido en una corrección.
  const porUnidades = Number.isInteger(detalle.cantidad)
  const [cuantos, setCuantos] = useState(porUnidades ? 1 : detalle.cantidad)
  const [motivo, setMotivo] = useState('')
  const [codigo, setCodigo] = useState('')
  const [conCodigo, setConCodigo] = useState(pideCodigo)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function quitar() {
    if (!motivo.trim()) {
      setError('Escribe o escoge por qué se quita.')
      return
    }
    setEnviando(true)
    setError(null)
    try {
      const pedido = await api.post<Pedido>(
        `/pedidos/${pedidoId}/items/${detalle.id}/quitar`,
        {
          cantidad: cuantos,
          motivo: motivo.trim(),
          codigo_autorizacion: conCodigo ? codigo.trim() || null : null,
        },
      )
      alTerminar(pedido)
    } catch (fallo) {
      // El servidor dijo que hace falta el código: se muestra el campo.
      if (fallo instanceof ErrorApi && fallo.estado === 403) setConCodigo(true)
      setError(fallo instanceof Error ? fallo.message : 'No se pudo quitar.')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div
      className="velo"
      role="dialog"
      aria-modal="true"
      aria-labelledby="titulo-corregir"
      // En la caja, un clic adentro no debe devolver el cursor al escáner.
      data-conserva-foco
    >
      <div className="confirmacion corregir">
        <h2 id="titulo-corregir" className="confirmacion-titulo">
          Quitar de la mesa
        </h2>
        <p className="confirmacion-nota">
          {detalle.nombre}
          {detalle.notas && ` (${detalle.notas})`} · en la mesa hay{' '}
          {formatoCantidad(detalle.cantidad)}
        </p>

        {porUnidades && detalle.cantidad > 1 && (
          <div className="corregir-cuantos">
            <span className="etiqueta">¿Cuántos quitar?</span>
            <span className="stepper">
              <button
                onClick={() => setCuantos((c) => Math.max(1, c - 1))}
                disabled={cuantos <= 1}
                aria-label="Quitar uno menos"
              >
                −
              </button>
              <span className="stepper-cantidad num">{cuantos}</span>
              <button
                onClick={() => setCuantos((c) => Math.min(detalle.cantidad, c + 1))}
                disabled={cuantos >= detalle.cantidad}
                aria-label="Quitar uno más"
              >
                +
              </button>
            </span>
          </div>
        )}

        <div className="chips">
          {MOTIVOS.map((m) => (
            <button
              key={m}
              className={`chip ${motivo === m ? 'activo' : ''}`}
              onClick={() => setMotivo(m)}
            >
              {m}
            </button>
          ))}
        </div>
        <input
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="¿Por qué se quita?"
          maxLength={200}
        />

        {conCodigo && (
          <>
            <span className="pista">
              Esta corrección la tiene que autorizar un administrador con su código.
            </span>
            <input
              type="password"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              placeholder="Código de administrador"
              autoComplete="off"
            />
          </>
        )}

        {error && <p className="aviso aviso-error">{error}</p>}

        <div className="confirmacion-botones">
          <button className="btn-secundario" onClick={cancelar} disabled={enviando}>
            No quitar nada
          </button>
          <button className="btn-peligro-lleno" onClick={() => void quitar()} disabled={enviando}>
            {enviando
              ? 'Quitando…'
              : `Quitar ${formatoCantidad(cuantos)} · ${plata(cuantos * detalle.precio_unitario)}`}
          </button>
        </div>
      </div>
    </div>
  )
}
