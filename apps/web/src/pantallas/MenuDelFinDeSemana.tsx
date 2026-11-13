import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { api } from '../api/cliente'
import type { Plato } from '../api/tipos'
import { leerPesos, milesAlEscribir, plata } from '../formato'

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

/** "13 a 15 nov" — corto, para que quepa en una línea del pie de la ficha. */
function rango(desde: string, hasta: string) {
  const d = new Date(`${desde}T12:00:00`)
  const h = new Date(`${hasta}T12:00:00`)
  const diaSolo = d.toLocaleDateString('es-CO', { day: 'numeric' })
  const conMes = (x: Date) => x.toLocaleDateString('es-CO', { day: 'numeric', month: 'short' })
  return `${d.getMonth() === h.getMonth() ? diaSolo : conMes(d)} a ${conMes(h)}`
}

/** "Ajiaco, Mondongo y 2 más" — para el resumen de lo que se va a publicar. */
function enumerar(nombres: string[]) {
  if (nombres.length <= 2) return nombres.join(' y ')
  return `${nombres.slice(0, 2).join(', ')} y ${nombres.length - 2} más`
}

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

  const marcados = useMemo(
    () => especiales.filter((p) => elegidos.has(p.id)).map((p) => p.nombre),
    [especiales, elegidos],
  )

  function marcar(id: number) {
    setElegidos((antes) => {
      const ahora = new Set(antes)
      if (ahora.has(id)) ahora.delete(id)
      else ahora.add(id)
      return ahora
    })
  }

  function abrirEditor(id: number) {
    setAbierto(abierto === id ? null : id)
    setPrecioNuevo('')
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

  async function guardarPlato(plato: Plato) {
    if (precioNuevo.trim() === '') {
      setAbierto(null)
      return
    }

    const valor = leerPesos(precioNuevo)
    if (valor === null || valor <= 0) {
      setError('El precio tiene que ser mayor que cero.')
      return
    }

    setError(null)
    try {
      await api.patch<Plato>(`/platos/${plato.id}`, { precio: valor })
      setListo(`${plato.nombre} ahora se vende a ${plata(valor)}.`)
      setPrecioNuevo('')
      setAbierto(null)
      cargar()
    } catch (fallo) {
      setError(fallo instanceof Error ? fallo.message : 'No se pudo guardar.')
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

  /** El editor, igual para un plato que rota y para uno fijo.
   *
   *  Solo el precio. El restaurante se maneja por lo que cobra el plato; el
   *  costo de la mercancía es cosa de la tienda, que es otro negocio y
   *  tiene su propia pantalla.
   */
  function editor(p: Plato) {
    return (
      <div className="plato-editor">
        <label className="campo-mini campo-precio-plato">
          <small>Se vende a</small>
          <input
            className="num"
            inputMode="numeric"
            value={milesAlEscribir(precioNuevo)}
            placeholder={milesAlEscribir(String(p.precio))}
            onFocus={(e) => e.target.select()}
            onChange={(e) => setPrecioNuevo(milesAlEscribir(e.target.value))}
          />
        </label>
        <button
          type="button"
          className="btn-secundario btn-angosto"
          onClick={() => void guardarPlato(p)}
        >
          Guardar
        </button>

        {/* Quitar de la carta se va al otro extremo de la fila, para que no
            quede pegado a «Guardar». */}
        {p.tipo === 'especial' && (
          <div className="plato-editor-aparte">
            <button type="button" className="btn-peligro" onClick={() => void quitar(p)}>
              Quitar de la carta
            </button>
          </div>
        )}
      </div>
    )
  }

  function tarjetaQueRota(p: Plato) {
    const elegido = elegidos.has(p.id)
    const editando = abierto === p.id
    return (
      <article
        key={p.id}
        className={`plato-tarjeta ${elegido ? 'elegido' : ''} ${editando ? 'editando' : ''}`}
      >
        <button
          type="button"
          className="plato-tarjeta-cuerpo"
          onClick={() => marcar(p.id)}
          aria-pressed={elegido}
        >
          <span className="plato-check" aria-hidden="true" />
          <span className="plato-nombre">{p.nombre}</span>
          <span className="plato-precio num">{plata(p.precio)}</span>
        </button>

        <div className="plato-tarjeta-pie">
          {p.activo_desde && p.activo_hasta ? (
            <span className="plato-vigente">
              en el menú · {rango(p.activo_desde, p.activo_hasta)}
            </span>
          ) : (
            <span className="plato-guardado">guardado en la carta</span>
          )}
          <button
            type="button"
            className="btn-tenue"
            onClick={() => abrirEditor(p.id)}
            aria-expanded={editando}
          >
            {editando ? 'Cerrar' : 'Editar'}
          </button>
        </div>

        {editando && editor(p)}
      </article>
    )
  }

  function tarjetaFija(p: Plato) {
    const editando = abierto === p.id
    return (
      <article key={p.id} className={`plato-tarjeta fijo ${editando ? 'editando' : ''}`}>
        <div className="plato-tarjeta-cuerpo">
          <span className="plato-siempre">siempre</span>
          <span className="plato-nombre">{p.nombre}</span>
          <span className="plato-precio num">{plata(p.precio)}</span>
        </div>

        <div className="plato-tarjeta-pie">
          <span className="plato-guardado">no se marca</span>
          <button
            type="button"
            className="btn-tenue"
            onClick={() => abrirEditor(p.id)}
            aria-expanded={editando}
          >
            {editando ? 'Cerrar' : 'Editar'}
          </button>
        </div>

        {editando && editor(p)}
      </article>
    )
  }

  const fechasAlReves = Boolean(desde && hasta && hasta < desde)
  // Un menú con fechas pasadas se guarda pero no le sale a nadie: el mesero
  // solo ve lo vigente hoy. Sin este aviso parece que el botón no sirviera.
  const fechasYaPasaron = Boolean(hasta && hasta < aISO(new Date()))

  return (
    <section className="tarjeta">
      <div className="menu-fds">
        <header className="menu-cabecera">
          <div className="menu-cabecera-texto">
            <h3>Menú del fin de semana</h3>
            <p className="pista">
              El restaurante abre sábado y domingo. Marca los platos que salen y
              publícalos: lo que no marques deja de aparecerle al mesero, pero sigue
              guardado en la carta para otro fin de semana.
            </p>
          </div>
          <div className="menu-fechas">
            <label className="campo-mini">
              <small>Desde</small>
              <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
            </label>
            <label className="campo-mini">
              <small>Hasta</small>
              <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
            </label>
          </div>
        </header>

        {error && <p className="aviso aviso-error">{error}</p>}
        {listo && <p className="aviso aviso-ok">{listo}</p>}
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

        {platos === null && <p className="cargando">Cargando la carta…</p>}

        {platos !== null && (
          <>
            <h4 className="menu-titulo">
              Platos que rotan
              <span className="menu-conteo">
                {elegidos.size === 0
                  ? 'ninguno marcado'
                  : `${elegidos.size} ${elegidos.size === 1 ? 'marcado' : 'marcados'}`}
              </span>
            </h4>

            {especiales.length === 0 ? (
              <p className="pista">
                Todavía no hay platos que roten. Agrega el primero aquí abajo.
              </p>
            ) : (
              <div className="platos-grilla">{especiales.map(tarjetaQueRota)}</div>
            )}

            {especiales.length > 0 && (
              <div className="menu-publicar">
                <span className="menu-publicar-resumen">
                  {elegidos.size === 0 ? (
                    'Sin platos marcados: el mesero solo vería los fijos.'
                  ) : (
                    <>
                      {enumerar(marcados)} · {dia(desde)} a {dia(hasta)}
                    </>
                  )}
                </span>
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
              </div>
            )}

            {fijos.length > 0 && (
              <>
                <h4 className="menu-titulo">
                  Siempre en la carta
                  <span className="menu-conteo">van todos los fines de semana</span>
                </h4>
                <div className="platos-grilla">{fijos.map(tarjetaFija)}</div>
              </>
            )}

            <form className="plato-nuevo" onSubmit={crear}>
              <label className="campo-mini campo-nombre">
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
                  value={milesAlEscribir(precio)}
                  onChange={(e) => setPrecio(milesAlEscribir(e.target.value))}
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
