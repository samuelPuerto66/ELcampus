import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '../api/cliente'
import type {
  Comparacion,
  Novedad,
  NovedadesDia,
  Producto,
  ResumenDia,
  TurnoCaja,
} from '../api/tipos'
import { cantidad as formatoCantidad, hora, plata } from '../formato'
import { useSesion } from '../sesion'
import CargarProductos from './CargarProductos'
import Catalogo from './Catalogo'
import Fiados from './Fiados'
import Usuarios from './Usuarios'
import Fondo from './Fondo'

type Pestana = 'resumen' | 'costos' | 'cargar' | 'fiado' | 'usuarios'

const PESTANAS: { valor: Pestana; texto: string }[] = [
  { valor: 'resumen', texto: 'Resumen' },
  { valor: 'costos', texto: 'Costos' },
  { valor: 'cargar', texto: 'Cargar' },
  { valor: 'fiado', texto: 'Fiado' },
  { valor: 'usuarios', texto: 'Usuarios' },
]

/** Una línea de "Para revisar hoy": qué pasó, cuánto, quién y por qué. */
function FilaNovedad({
  tipo,
  grave,
  novedad: n,
}: {
  tipo: string
  grave?: boolean
  novedad: Novedad
}) {
  return (
    <div className="novedad">
      <span className={`novedad-tipo ${grave ? 'anulacion' : ''}`}>{tipo}</span>
      <span className="novedad-texto">
        <b className="num">{plata(n.monto)}</b> · {n.quien} · {hora(n.hora)}
        {n.con_codigo && ' · con código de admin'}
        {n.que && <small>{n.que}</small>}
        {n.motivo && <small>«{n.motivo}»</small>}
      </span>
    </div>
  )
}

function Resumen() {
  const [resumen, setResumen] = useState<ResumenDia | null>(null)
  const [comparacion, setComparacion] = useState<Comparacion | null>(null)
  const [alertas, setAlertas] = useState<Producto[]>([])
  const [cierres, setCierres] = useState<TurnoCaja[]>([])
  const [novedades, setNovedades] = useState<NovedadesDia | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<ResumenDia>('/reportes/dia'),
      api.get<Comparacion>('/reportes/comparar'),
      api.get<Producto[]>('/inventario/alertas'),
      api.get<TurnoCaja[]>('/caja?limite=7'),
      api.get<NovedadesDia>('/reportes/novedades'),
    ])
      .then(([r, c, a, t, n]) => {
        setResumen(r)
        setComparacion(c)
        setAlertas(a)
        setCierres(t)
        setNovedades(n)
      })
      .catch((fallo) =>
        setError(fallo instanceof Error ? fallo.message : 'No se pudieron cargar los datos.'),
      )
  }, [])

  if (error) return <p className="aviso aviso-error">{error}</p>
  if (!resumen) return <p className="cargando">Cargando…</p>

  const variacion = comparacion?.variacion_porcentaje ?? null
  const hoy = new Date(`${resumen.fecha}T12:00:00`).toLocaleDateString('es-CO', {
    weekday: 'long',
    day: 'numeric',
    month: 'short',
  })

  return (
    <div className="panel-rejilla">
      <section className="tarjeta tarjeta-ancha">
        <div className="admin-hoy">
          <span className="etiqueta">Ventas de hoy · {hoy}</span>
          <span className="admin-total num">{plata(resumen.total)}</span>
          {variacion !== null && (
            <span className={`delta ${variacion >= 0 ? 'sube' : 'baja'}`}>
              {variacion >= 0 ? '▲' : '▼'} {Math.abs(variacion)}% vs. hace una semana
            </span>
          )}
        </div>

        <div className="tiles">
          <div className="tile">
            <span className="tile-valor num">{resumen.cantidad_ventas}</span>
            <span className="tile-clave">ventas</span>
          </div>
          <div className="tile">
            <span className="tile-valor num">{plata(resumen.ticket_promedio)}</span>
            <span className="tile-clave">promedio</span>
          </div>
          <div className="tile">
            <span className="tile-valor num">{resumen.mesas_atendidas}</span>
            <span className="tile-clave">mesas</span>
          </div>
        </div>

        <div className="utilidad">
          <div className="tile">
            <span
              className={`tile-valor num ${resumen.utilidad >= 0 ? 'positivo' : 'negativo'}`}
            >
              {plata(resumen.utilidad)}
            </span>
            <span className="tile-clave">
              te quedaron
              {resumen.margen_porcentaje !== null && ` · ${resumen.margen_porcentaje}%`}
            </span>
          </div>
          <div className="tile">
            <span className="tile-valor num">{plata(resumen.costo)}</span>
            <span className="tile-clave">te costó la mercancía</span>
          </div>
        </div>

        {(resumen.propinas > 0 || resumen.descuentos > 0) && (
          <div className="utilidad">
            <div className="tile">
              <span className="tile-valor num">{plata(resumen.propinas)}</span>
              <span className="tile-clave">de propina para los empleados</span>
            </div>
            <div className="tile">
              <span className="tile-valor num">{plata(resumen.descuentos)}</span>
              <span className="tile-clave">
                en descuentos y cortesías
                {resumen.cantidad_descuentos > 0 && ` · ${resumen.cantidad_descuentos}`}
              </span>
            </div>
          </div>
        )}

        {(resumen.fiado_del_dia > 0 || resumen.te_deben > 0) && (
          <div className="tiles">
            <div className="tile">
              <span className="tile-valor num">{plata(resumen.fiado_del_dia)}</span>
              <span className="tile-clave">fiado hoy</span>
            </div>
            <div className="tile">
              <span className="tile-valor num">{plata(resumen.abonos_del_dia)}</span>
              <span className="tile-clave">abonaron hoy</span>
            </div>
            <div className="tile">
              <span className="tile-valor num debe">{plata(resumen.te_deben)}</span>
              <span className="tile-clave">te deben en total</span>
            </div>
          </div>
        )}

        {resumen.lineas_sin_costo > 0 && (
          <p className="aviso-costo">
            Hay {resumen.lineas_sin_costo}{' '}
            {resumen.lineas_sin_costo === 1 ? 'producto vendido' : 'productos vendidos'} sin
            costo cargado, así que lo que te quedó es en realidad menos de lo que dice.
            Cárgales el costo para ver la cifra de verdad.
          </p>
        )}
      </section>

      {alertas.length > 0 && (
        <section className="tarjeta">
          <h2 className="tarjeta-titulo">Se está acabando</h2>
          {alertas.map((producto) => (
            <div key={producto.id} className="fila-lista">
              <span>{producto.nombre}</span>
              <span className="chip-bajo num">
                {formatoCantidad(producto.stock_actual)}{' '}
                {producto.tipo_venta === 'peso' ? 'kg' : 'und'}
              </span>
            </div>
          ))}
        </section>
      )}

      {resumen.por_metodo.length > 0 && (
        <section className="tarjeta">
          <h2 className="tarjeta-titulo">Cómo entró la plata</h2>
          {resumen.por_metodo.map((m) => (
            <div key={m.metodo_pago} className="fila-lista">
              <span className="capitalizado">{m.metodo_pago}</span>
              <span className="valor-tenue num">
                {plata(m.total)} · {m.cantidad}
              </span>
            </div>
          ))}
        </section>
      )}

      {resumen.mas_vendidos.length > 0 && (
        <section className="tarjeta">
          <h2 className="tarjeta-titulo">Lo que más se vendió</h2>
          {resumen.mas_vendidos.map((p) => (
            <div key={p.nombre} className="fila-lista">
              <span>{p.nombre}</span>
              <span className="valor-tenue num">
                {formatoCantidad(p.cantidad)} · {plata(p.total)}
              </span>
            </div>
          ))}
        </section>
      )}

      {cierres.length > 0 && (
        <section className="tarjeta">
          <h2 className="tarjeta-titulo">Cierres de caja</h2>
          {cierres.map((c) => (
            <div key={c.id} className="fila-lista">
              <span>
                {new Date(c.hora_apertura).toLocaleDateString('es-CO', {
                  weekday: 'short',
                  day: 'numeric',
                })}{' '}
                · {c.usuario_nombre}
              </span>
              {c.estado === 'abierto' ? (
                <span className="valor-tenue">abierta desde {hora(c.hora_apertura)}</span>
              ) : c.diferencia === 0 ? (
                <span className="chip-cuadra">cuadró</span>
              ) : (
                <span className={(c.diferencia ?? 0) < 0 ? 'chip-bajo num' : 'chip-sobra num'}>
                  {(c.diferencia ?? 0) < 0 ? 'faltaron' : 'sobraron'}{' '}
                  {plata(Math.abs(c.diferencia ?? 0))}
                </span>
              )}
            </div>
          ))}
        </section>
      )}

      {novedades &&
        novedades.anulaciones.length +
          novedades.descuentos.length +
          novedades.correcciones.length >
          0 && (
          <section className="tarjeta">
            <h2 className="tarjeta-titulo">Para revisar hoy</h2>
            <p className="tarjeta-nota">
              Cada vez que alguien anuló una venta, rebajó una cuenta o le quitó algo a una
              mesa. Si algo no te cuadra, pregúntale a quien lo hizo.
            </p>
            {novedades.anulaciones.map((n) => (
              <FilaNovedad key={`a-${n.id}`} tipo="Anulada" grave novedad={n} />
            ))}
            {novedades.descuentos.map((n) => (
              <FilaNovedad key={`d-${n.id}`} tipo="Descuento" novedad={n} />
            ))}
            {novedades.correcciones.map((n) => (
              <FilaNovedad key={`c-${n.id}`} tipo="Corrección" novedad={n} />
            ))}
          </section>
        )}
    </div>
  )
}

export default function Admin() {
  const { sesion, salir } = useSesion()
  const [pestana, setPestana] = useState<Pestana>('resumen')

  return (
    <div className="panel">
      <Fondo />
      <header className="barra">
        <span className="marca">EL CAMPUS</span>
        <nav className="pestanas">
          {PESTANAS.map((p) => (
            <button
              key={p.valor}
              className={`pestana ${pestana === p.valor ? 'activa' : ''}`}
              onClick={() => setPestana(p.valor)}
            >
              {p.texto}
            </button>
          ))}
        </nav>
        <span className="der">
          <span className="quien">{sesion?.nombre}</span>
          <Link className="btn-peligro" to="/caja">
            Caja
          </Link>
          <button className="btn-peligro" onClick={salir}>
            Salir
          </button>
        </span>
      </header>

      <div className="panel-cuerpo">
        {pestana === 'resumen' && <Resumen />}
        {pestana === 'costos' && <Catalogo />}
        {pestana === 'cargar' && <CargarProductos />}
        {pestana === 'fiado' && (
          <section className="tarjeta">
            <Fiados esAdmin />
          </section>
        )}
        {pestana === 'usuarios' && <Usuarios />}
      </div>
    </div>
  )
}
