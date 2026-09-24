import { useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/cliente'
import type { Rol, Usuario } from '../api/tipos'
import { useSesion } from '../sesion'

const ROLES: { valor: Rol; texto: string; explica: string }[] = [
  { valor: 'mesero', texto: 'Mesero', explica: 'Toma pedidos en las mesas desde el celular.' },
  { valor: 'vendedor', texto: 'Vendedor', explica: 'Cobra en la caja y maneja el inventario.' },
  {
    valor: 'administrador',
    texto: 'Administrador',
    explica: 'Puede todo lo anterior, más precios y usuarios. Necesita el código de acceso.',
  },
]

const CLAVE_MINIMA = 6

export default function Usuarios() {
  const { sesion } = useSesion()
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [listo, setListo] = useState<string | null>(null)

  // alta
  const [nombre, setNombre] = useState('')
  const [correo, setCorreo] = useState('')
  const [rol, setRol] = useState<Rol>('mesero')
  const [clave, setClave] = useState('')
  const [guardando, setGuardando] = useState(false)

  // edición: el id de la fila abierta y lo que se está cambiando
  const [abierto, setAbierto] = useState<number | null>(null)
  const [claveNueva, setClaveNueva] = useState('')
  const [rolNuevo, setRolNuevo] = useState<Rol>('mesero')

  function cargar() {
    api
      .get<Usuario[]>('/auth/usuarios')
      .then(setUsuarios)
      .catch((f) => setError(f instanceof Error ? f.message : 'No se pudo cargar la lista.'))
  }

  useEffect(cargar, [])

  function avisar(mensaje: string) {
    setListo(mensaje)
    setError(null)
    setTimeout(() => setListo(null), 4000)
  }

  async function registrar(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setListo(null)

    if (clave.length < CLAVE_MINIMA) {
      setError(`La clave necesita al menos ${CLAVE_MINIMA} caracteres.`)
      return
    }

    setGuardando(true)
    try {
      await api.post<Usuario>('/auth/usuarios', {
        nombre: nombre.trim(),
        correo: correo.trim() || null,
        rol,
        clave,
      })
      avisar(`${nombre.trim()} ya puede entrar.`)
      setNombre('')
      setCorreo('')
      setClave('')
      setRol('mesero')
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo registrar.')
    } finally {
      setGuardando(false)
    }
  }

  async function cambiar(usuario: Usuario, cambios: Record<string, unknown>, aviso: string) {
    setError(null)
    try {
      await api.patch<Usuario>(`/auth/usuarios/${usuario.id}`, cambios)
      avisar(aviso)
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar el cambio.')
    }
  }

  function abrir(usuario: Usuario) {
    const mismo = abierto === usuario.id
    setAbierto(mismo ? null : usuario.id)
    setClaveNueva('')
    setRolNuevo(usuario.rol)
    setError(null)
  }

  return (
    <div className="panel-rejilla">
      {/* ------------------------------------------------- registrar */}
      <section className="tarjeta">
        <h2 className="tarjeta-titulo">Registrar usuario</h2>
        <p className="tarjeta-nota">
          Quien quede registrado entra con su nombre o su correo, y la app lo lleva a la
          pantalla que le toca según el rol.
        </p>

        <form className="forma" onSubmit={registrar}>
          <label className="campo">
            <span className="etiqueta">Nombre de usuario</span>
            <input
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="carlos"
              autoComplete="off"
              required
            />
          </label>

          <label className="campo">
            <span className="etiqueta">Correo (opcional)</span>
            <input
              type="email"
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
              placeholder="carlos@elcampus.co"
              autoComplete="off"
            />
          </label>

          <div className="campo">
            <span className="etiqueta">Qué hace en el negocio</span>
            <div className="roles">
              {ROLES.map((r) => (
                <button
                  key={r.valor}
                  type="button"
                  className={`rol ${rol === r.valor ? 'activo' : ''}`}
                  aria-pressed={rol === r.valor}
                  onClick={() => setRol(r.valor)}
                >
                  {r.texto}
                </button>
              ))}
            </div>
            <small className="pista">{ROLES.find((r) => r.valor === rol)!.explica}</small>
          </div>

          <label className="campo">
            <span className="etiqueta">Clave para entrar</span>
            <input
              type="password"
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              placeholder="Mínimo 6 caracteres"
              autoComplete="new-password"
              required
            />
          </label>

          <button className="btn-primario" type="submit" disabled={guardando}>
            {guardando ? 'Registrando…' : 'Registrar'}
          </button>
        </form>
      </section>

      {/* ---------------------------------------------------- lista */}
      <section className="tarjeta">
        <h2 className="tarjeta-titulo">
          Usuarios del negocio
          {usuarios && <span className="conteo">{usuarios.length}</span>}
        </h2>

        {error && <p className="aviso aviso-error">{error}</p>}
        {listo && <p className="aviso aviso-ok">{listo}</p>}

        {usuarios === null && <p className="cargando">Cargando…</p>}

        {usuarios?.map((u) => {
          const soyYo = u.id === sesion?.id
          return (
            <div key={u.id} className={`usuario ${u.activo ? '' : 'apagado'}`}>
              <button type="button" className="usuario-fila" onClick={() => abrir(u)}>
                <span className="usuario-quien">
                  <b>
                    {u.nombre}
                    {soyYo && <span className="tu"> tú</span>}
                  </b>
                  <small>{u.correo ?? 'sin correo'}</small>
                </span>
                <span className={`chip-rol ${u.rol}`}>{u.rol}</span>
                {!u.activo && <span className="chip-apagado">inactivo</span>}
              </button>

              {abierto === u.id && (
                <div className="usuario-editar">
                  <div className="campo">
                    <span className="etiqueta">Cambiar rol</span>
                    <div className="roles">
                      {ROLES.map((r) => (
                        <button
                          key={r.valor}
                          type="button"
                          className={`rol ${rolNuevo === r.valor ? 'activo' : ''}`}
                          onClick={() => setRolNuevo(r.valor)}
                        >
                          {r.texto}
                        </button>
                      ))}
                    </div>
                    {rolNuevo !== u.rol && (
                      <button
                        type="button"
                        className="btn-secundario"
                        onClick={() => cambiar(u, { rol: rolNuevo }, `${u.nombre} ahora es ${rolNuevo}.`)}
                      >
                        Guardar rol
                      </button>
                    )}
                  </div>

                  <div className="campo">
                    <span className="etiqueta">Ponerle una clave nueva</span>
                    <input
                      type="password"
                      value={claveNueva}
                      onChange={(e) => setClaveNueva(e.target.value)}
                      placeholder="Mínimo 6 caracteres"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      className="btn-secundario"
                      disabled={claveNueva.length < CLAVE_MINIMA}
                      onClick={() => {
                        cambiar(u, { clave: claveNueva }, `Clave de ${u.nombre} cambiada.`)
                        setClaveNueva('')
                      }}
                    >
                      Cambiar clave
                    </button>
                  </div>

                  {!soyYo && (
                    <button
                      type="button"
                      className={u.activo ? 'btn-peligro' : 'btn-secundario'}
                      onClick={() =>
                        cambiar(
                          u,
                          { activo: !u.activo },
                          u.activo
                            ? `${u.nombre} ya no puede entrar.`
                            : `${u.nombre} puede entrar otra vez.`,
                        )
                      }
                    >
                      {u.activo ? 'Desactivar usuario' : 'Reactivar usuario'}
                    </button>
                  )}
                  {soyYo && (
                    <small className="pista">
                      No puedes desactivarte ni quitarte el cargo a ti mismo.
                    </small>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </section>
    </div>
  )
}
