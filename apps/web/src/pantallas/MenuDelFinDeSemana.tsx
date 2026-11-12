import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { api } from '../api/cliente'
import type { Plato } from '../api/tipos'
import { leerPesos, plata } from '../formato'

/** yyyy-mm-dd en hora local.
 *
 *  A propósito no se usa `toISOString()`: esa fecha es UTC y en Colombia
 *  (UTC-5) un viernes por la noche saldría como sábado, que es justo el día
 *  en que el menú tiene que estar bien.
 */
function aISO(fecha: Date) {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

/** El fin de semana que viene — o el que está corriendo, si hoy ya es
 *  viernes, sábado o domingo. */
function finDeSemana() {
  const hoy = new Date()
  const dia = hoy.getDay() // 0 domingo … 6 sábado
  const viernes = new Date(hoy)
  if (dia === 0) viernes.setDate(hoy.getDate() - 2)
  else if (dia === 6) viernes.setDate(hoy.getDate() - 1)
  else if (dia < 5) viernes.setDate(hoy.getDate() + (5 - dia))

  const domingo = new Date(viernes)
  domingo.setDate(viernes.getDate() + 2)
  return { desde: aISO(viernes), hasta: aISO(domingo) }
}

const dia = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('es-CO', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })

export default function MenuDelFinDeSemana() {
  const [platos, setPlatos] = useState<Plato[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [listo, setListo] = useState<string | null>(null)

  const [elegidos, setElegidos] = useState<Set<number>>(new Set())
  const [desde, setDesde] = useState(finDeSemana().desde)
  const [hasta, setHasta] = useState(finDeSemana().hasta)
  const [publicando, setPublicando] = useState(false)

  const [abierto, setAbierto] = useState<number | null>(null)
  const [precioNuevo, setPrecioNuevo] = useState('')

  const [nombre, setNombre] = useState('')
  const [precio, setPrecio] = useState('')
  const [guardando, setGuardando] = useState(false)

  /** Trae la carta completa, no el menú de hoy: el administrador arma el fin
   *  de semana escogiendo entre todos los platos que existen.
   *
   *  Abre siempre en limpio —nada marcado, fechas del próximo fin de
   *  semana—. Arrancar marcando lo que ya está publicado invita a darle
   *  publicar con las fechas viejas y dejar el menú para unos días que ya
   *  pasaron, que es como si el botón no sirviera.
   */
  function cargar() {
    api
      .get<Plato[]>('/platos?solo_vigentes=false')
      .then(setPlatos)
      .catch((f) => setError(f instanceof Error ? f.message : 'No se pudo cargar la carta.'))
  }

  useEffect(cargar, [])

  useEffect(() => {
    if (!listo) return
    const reloj = setTimeout(() => setListo(null), 6000)
    return () => clearTimeout(reloj)
  }, [listo])

  const especiales = useMemo(
    () => (platos ?? []).filter((p) => p.tipo === 'especial'),
    [platos],
  )
  const fijos = useMemo(() => (platos ?? []).filter((p) => p.tipo === 'fijo'), [platos])

  function marcar(id: number) {
    setElegidos((antes) => {
      const ahora = new Set(antes)
      if (ahora.has(id)) ahora.delete(id)
      else ahora.add(id)
      return ahora
    })
  }

  async function publicar() {
    setError(null)
    setPublicando(true)
    try {
      await api.post<Plato[]>('/platos/menu', { desde, hasta, platos: [...elegidos] })
      setListo(
        elegidos.size === 0
          ? 'Se publicó exitosamente el menú: van solo los platos fijos.'
          : `Se publicó exitosamente el menú · ${elegidos.size} ${
              elegidos.size === 1 ? 'plato' : 'platos'
            } del ${dia(desde)} al ${dia(hasta)}.`,
      )
      setElegidos(new Set())
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo publicar el menú.')
    } finally {
      setPublicando(false)
    }
  }

  async function crear(e: FormEvent) {
    e.preventDefault()
    const valor = leerPesos(precio)
    if (!nombre.trim()) {
      setError('Ponle un nombre al plato.')
      return
    }
    if (valor === null || valor <= 0) {
      setError('El precio del plato tiene que ser mayor que cero.')
      return
    }

    setError(null)
    setGuardando(true)
    try {
      await api.post<Plato>('/platos', {
        nombre: nombre.trim(),
        precio: valor,
        tipo: 'especial',
      })
      setListo(`${nombre.trim()} quedó en la carta. Márcalo cuando vaya a salir.`)
      setNombre('')
      setPrecio('')
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo agregar el plato.')
    } finally {
      setGuardando(false)
    }
  }

  async function cambiarPrecio(plato: Plato) {
    const valor = leerPesos(precioNuevo)
    if (valor === null || valor <= 0) {
      setError('El precio tiene que ser mayor que cero.')
      return
    }
    setError(null)
    try {
      await api.patch<Plato>(`/platos/${plato.id}`, { precio: valor })
      setListo(`${plato.nombre} ahora vale ${plata(valor)}.`)
      setPrecioNuevo('')
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo cambiar el precio.')
    }
  }

  async function quitar(plato: Plato) {
    if (!window.confirm(`¿Quitar "${plato.nombre}" de la carta? Ya no lo podrás volver a sacar.`))
      return
    setError(null)
    try {
      await api.borrar(`/platos/${plato.id}`)
      setElegidos((antes) => {
        const ahora = new Set(antes)
        ahora.delete(plato.id)
        return ahora
      })
      setAbierto(null)
      setListo(`${plato.nombre} salió de la carta.`)
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo quitar el plato.')
    }
  }

  const fechasAlReves = Boolean(desde && hasta && hasta < desde)
  // Un menú con fechas pasadas se guarda pero no le sale a nadie: el mesero
  // solo ve lo vigente hoy. Sin este aviso parece que el botón no sirviera.
  const fechasYaPasaron = Boolean(hasta && hasta < aISO(new Date()))

  return (
    <section className="tarjeta">
      <div className="catalogo">
        <p className="pista">
          Cada fin de semana cambian los platos. Marca los que salen y publícalos: lo que
          no marques deja de aparecerle al mesero, y el menú se apaga solo cuando pasa la
          fecha. La picada, la pechuga y la mojarra van siempre y no se marcan.
        </p>

        {error && <p className="aviso aviso-error">{error}</p>}
        {listo && <p className="aviso aviso-ok">{listo}</p>}

        {platos === null && <p className="cargando">Cargando la carta…</p>}

        {platos !== null && (
          <>
            <div className="fechas-menu">
              <label className="campo-mini">
                <small>Desde</small>
                <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
              </label>
              <label className="campo-mini">
                <small>Hasta</small>
                <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
              </label>
            </div>

            {fechasAlReves && (
              <p className="aviso aviso-error">
                La fecha de fin no puede ser anterior a la de inicio.
              </p>
            )}
            {fechasYaPasaron && !fechasAlReves && (
              <p className="aviso aviso-atencion">
                Ese fin de semana ya pasó. Si publicas con estas fechas, el menú queda
                guardado pero no le aparece al mesero.
              </p>
            )}

            {especiales.length === 0 && (
              <p className="pista">
                Todavía no hay platos que roten. Agrega el primero aquí abajo.
              </p>
            )}

            {especiales.map((p) => (
              <div key={p.id} className={`plato-menu ${elegidos.has(p.id) ? 'elegido' : ''}`}>
                <div className="plato-menu-fila">
                  <label className="plato-menu-marca">
                    <input
                      type="checkbox"
                      checked={elegidos.has(p.id)}
                      onChange={() => marcar(p.id)}
                    />
                    <span className="plato-menu-quien">
                      <b>{p.nombre}</b>
                      {p.activo_desde && p.activo_hasta && (
                        <small>
                          en el menú · {dia(p.activo_desde)} a {dia(p.activo_hasta)}
                        </small>
                      )}
                    </span>
                  </label>
                  <span className="plato-menu-precio num">{plata(p.precio)}</span>
                  <button
                    type="button"
                    className="btn-tenue"
                    onClick={() => {
                      setAbierto(abierto === p.id ? null : p.id)
                      setPrecioNuevo('')
                    }}
                    aria-expanded={abierto === p.id}
                  >
                    Editar
                  </button>
                </div>

                {abierto === p.id && (
                  <div className="plato-menu-editar">
                    <label className="campo-mini">
                      <small>Cambiar precio</small>
                      <input
                        className="num"
                        inputMode="numeric"
                        value={precioNuevo}
                        placeholder={String(p.precio)}
                        onFocus={(e) => e.target.select()}
                        onChange={(e) => setPrecioNuevo(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn-secundario btn-angosto"
                      disabled={!precioNuevo.trim()}
                      onClick={() => void cambiarPrecio(p)}
                    >
                      Guardar precio
                    </button>
                    <button
                      type="button"
                      className="btn-peligro"
                      onClick={() => void quitar(p)}
                    >
                      Quitar de la carta
                    </button>
                  </div>
                )}
              </div>
            ))}

            {especiales.length > 0 && (
              <button
                className="btn-primario"
                onClick={() => void publicar()}
                disabled={publicando || fechasAlReves || fechasYaPasaron || !desde || !hasta}
              >
                {publicando
                  ? 'Publicando…'
                  : elegidos.size === 0
                    ? 'Publicar: solo los platos fijos'
                    : `Publicar el menú · ${elegidos.size} ${
                        elegidos.size === 1 ? 'plato' : 'platos'
                      }`}
              </button>
            )}

            {fijos.length > 0 && (
              <p className="pista">
                <b>Siempre en la carta:</b> {fijos.map((p) => p.nombre).join(' · ')}.
              </p>
            )}

            <form className="plato-nuevo" onSubmit={crear}>
              <label className="campo-mini">
                <small>Agregar un plato a la carta</small>
                <input
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  placeholder="Nombre del plato"
                  autoComplete="off"
                />
              </label>
              <label className="campo-mini">
                <small>Precio</small>
                <input
                  className="num"
                  inputMode="numeric"
                  value={precio}
                  onChange={(e) => setPrecio(e.target.value)}
                  placeholder="0"
                />
              </label>
              <button className="btn-secundario btn-angosto" type="submit" disabled={guardando}>
                {guardando ? 'Guardando…' : 'Agregar'}
              </button>
            </form>
          </>
        )}
      </div>
    </section>
  )
}
