import { useState } from 'react'

/** Lo que más se pide, a un toque. Si el menú cambia, se cambia esta lista. */
const NOTAS_RAPIDAS = ['Sin cebolla', 'Sin sal', 'Sin ensalada', 'Término medio', 'Bien asado']

/**
 * La nota de un plato para la cocina: "sin cebolla".
 *
 * Si la línea tiene varios platos, el mesero escoge si la nota es para
 * todos ("3 picadas sin cebolla") o solo para uno ("3 picadas, una sin
 * cebolla"); en ese caso la línea se parte en dos.
 */
export default function NotaDelPlato({
  nombre,
  cantidad,
  notaActual,
  alGuardar,
  cancelar,
}: {
  nombre: string
  cantidad: number
  notaActual: string | undefined
  alGuardar: (nota: string | null, soloUno: boolean) => void
  cancelar: () => void
}) {
  const [nota, setNota] = useState(notaActual ?? '')
  const varios = cantidad > 1

  const limpia = nota.trim() || null

  return (
    <div className="velo" role="dialog" aria-modal="true" aria-labelledby="titulo-nota">
      <div className="confirmacion corregir">
        <h2 id="titulo-nota" className="confirmacion-titulo">
          Nota para la cocina
        </h2>
        <p className="confirmacion-nota">{nombre}</p>

        <div className="chips">
          {NOTAS_RAPIDAS.map((rapida) => (
            <button
              key={rapida}
              className={`chip ${nota === rapida ? 'activo' : ''}`}
              onClick={() => setNota(rapida)}
            >
              {rapida}
            </button>
          ))}
        </div>
        <input
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder="Escribe la nota"
          maxLength={120}
        />

        <div className="confirmacion-botones">
          <button className="btn-secundario" onClick={cancelar}>
            Cancelar
          </button>
          {varios && limpia ? (
            <>
              <button className="btn-secundario" onClick={() => alGuardar(limpia, true)}>
                Solo para 1
              </button>
              <button className="btn-primario" onClick={() => alGuardar(limpia, false)}>
                Para los {cantidad}
              </button>
            </>
          ) : (
            <button className="btn-primario" onClick={() => alGuardar(limpia, false)}>
              {limpia ? 'Guardar nota' : 'Sin nota'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
