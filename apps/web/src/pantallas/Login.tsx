import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { borrarSesion, entrar as pedirSesion } from '../api/cliente'
import { pantallaDe, useSesion } from '../sesion'
import Fondo from './Fondo'

type TipoAcceso = 'administrador' | 'empleado'

const TIPOS: { valor: TipoAcceso; texto: string; icono: string }[] = [
  { valor: 'administrador', texto: 'Administrador', icono: '🛡' },
  { valor: 'empleado', texto: 'Empleado', icono: '👤' },
]

/** Los dos campos muestran lo mismo en blanco: la etiqueta de arriba ya dice
 *  cuál es cuál, y así no queda un nombre de ejemplo a la vista del cliente. */
const PUNTOS = '••••••••'

/** El turno que se está trabajando, para el pie de la tarjeta. */
function turnoAhora(): string {
  const hora = new Date().getHours()
  if (hora < 12) return 'Mañana'
  if (hora < 18) return 'Tarde'
  return 'Noche'
}

export default function Login() {
  const [tipo, setTipo] = useState<TipoAcceso>('empleado')
  const [nombre, setNombre] = useState('')
  const [clave, setClave] = useState('')
  const [codigo, setCodigo] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [nota, setNota] = useState<string | null>(null)
  const [entrando, setEntrando] = useState(false)
  const [enLinea, setEnLinea] = useState<boolean | null>(null)
  const { entrar } = useSesion()
  const navegar = useNavigate()

  const turno = useMemo(turnoAhora, [])

  // El indicador de arriba dice la verdad: pregunta si el servidor contesta.
  useEffect(() => {
    let vivo = true
    fetch('/api/salud')
      .then((r) => {
        if (vivo) setEnLinea(r.ok)
      })
      .catch(() => {
        if (vivo) setEnLinea(false)
      })
    return () => {
      vivo = false
    }
  }, [])

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setNota(null)
    setEntrando(true)
    try {
      const sesion = await pedirSesion(
        nombre.trim(),
        clave,
        tipo === 'administrador' ? codigo : undefined,
      )

      // Quien entra por Administrador tiene que serlo de verdad. La sesión ya
      // quedó guardada al pedirla, así que si no cuadra hay que borrarla.
      if (tipo === 'administrador' && sesion.rol !== 'administrador') {
        borrarSesion()
        setError('Esta cuenta no es de administrador. Entra como Empleado.')
        return
      }

      entrar(sesion)
      navegar(pantallaDe(sesion.rol), { replace: true })
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo entrar.')
    } finally {
      setEntrando(false)
    }
  }

  return (
    <div className="terminal">
      <Fondo />

      <main className="terminal-centro">
        <form className="tarjeta-acceso" onSubmit={enviar}>
          <div className="login-marca">
            {/* El logo ya trae el nombre y el lema, así que hace de título. */}
            <img
              className="logo-campus"
              src="/marca/logo.png"
              alt="El Campus · Bar, Grill, Fun &amp; Market"
              width={460}
              height={406}
            />
          </div>

          <div className="tipos">
            {TIPOS.map((t) => (
              <button
                key={t.valor}
                type="button"
                className={`tipo ${tipo === t.valor ? 'activo' : ''}`}
                aria-pressed={tipo === t.valor}
                onClick={() => {
                  setTipo(t.valor)
                  setError(null)
                  if (t.valor !== 'administrador') setCodigo('')
                }}
              >
                <span aria-hidden="true">{t.icono}</span> {t.texto}
              </button>
            ))}
          </div>

          <label className="campo">
            <span className="etiqueta">Tu nombre o correo</span>
            <span className="campo-caja">
              <i className="campo-icono" aria-hidden="true">
                🪪
              </i>
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder={PUNTOS}
                autoFocus
                autoComplete="username"
                required
              />
            </span>
          </label>

          <label className="campo">
            <span className="campo-cabeza">
              <span className="etiqueta">Clave de acceso</span>
              <button
                type="button"
                className="enlace-tenue"
                onClick={() => setNota('Pídele al administrador que te la cambie.')}
              >
                ¿Olvidaste tu clave?
              </button>
            </span>
            <span className="campo-caja">
              <i className="campo-icono" aria-hidden="true">
                🔑
              </i>
              <input
                type={verClave ? 'text' : 'password'}
                value={clave}
                onChange={(e) => setClave(e.target.value)}
                placeholder={PUNTOS}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="campo-ojo"
                aria-label={verClave ? 'Ocultar la clave' : 'Mostrar la clave'}
                onClick={() => setVerClave((v) => !v)}
              >
                {verClave ? '🙈' : '👁'}
              </button>
            </span>
          </label>

          {tipo === 'administrador' && (
            <label className="campo campo-codigo">
              <span className="etiqueta">Código de administrador</span>
              <span className="campo-caja">
                <i className="campo-icono" aria-hidden="true">
                  🛡
                </i>
                <input
                  type="password"
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  placeholder={PUNTOS}
                  autoComplete="one-time-code"
                  required
                />
              </span>
              <small className="pista">Además de tu clave. Solo lo saben los administradores.</small>
            </label>
          )}

          {error && <p className="aviso aviso-error">{error}</p>}
          {nota && <p className="aviso aviso-atencion">{nota}</p>}

          <button className="btn-entrar" type="submit" disabled={entrando}>
            {entrando ? (
              <>
                <i className="girando" aria-hidden="true" /> Verificando credenciales…
              </>
            ) : (
              <>
                Entrar al Sistema <span aria-hidden="true">→</span>
              </>
            )}
          </button>

          <div className="tarjeta-pie">
            <span className="estado-red">
              <i className={enLinea === false ? 'punto-mal' : 'punto-ok'} aria-hidden="true" />
              {enLinea === null ? 'Conectando…' : enLinea ? 'En línea' : 'Sin conexión'}
              <span className="separa">·</span> Turno: {turno}
            </span>
          </div>
        </form>
      </main>

      <footer className="terminal-pie">
        <span>© {new Date().getFullYear()} El Campus · Bar, Grill, Fun &amp; Market.</span>
        <span>Red local del negocio</span>
      </footer>
    </div>
  )
}
