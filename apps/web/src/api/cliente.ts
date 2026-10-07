import type { Sesion } from './tipos'

const LLAVE = 'elcampus.sesion'

export function leerSesion(): Sesion | null {
  try {
    const guardada = localStorage.getItem(LLAVE)
    return guardada ? (JSON.parse(guardada) as Sesion) : null
  } catch {
    return null
  }
}

export function guardarSesion(sesion: Sesion) {
  localStorage.setItem(LLAVE, JSON.stringify(sesion))
}

export function borrarSesion() {
  localStorage.removeItem(LLAVE)
}

/** El servidor contestó, pero que no. `estado` es el código HTTP. */
export class ErrorApi extends Error {
  constructor(
    mensaje: string,
    readonly estado: number,
  ) {
    super(mensaje)
  }
}

/** El servidor no contestó: se cayó el WiFi o el PC de la caja está apagado.
 *  Va aparte porque no es un "no": es un "todavía no se sabe", y el pedido
 *  del mesero se puede reintentar sin miedo. */
export class SinConexion extends Error {
  constructor() {
    super('Sin conexión con la caja. Revisa el WiFi del local.')
  }
}

// Si en este tiempo no contesta, se da por caído. En la red del local una
// respuesta normal llega en milisegundos; esperar más solo deja al mesero
// mirando un botón que no hace nada.
const ESPERA_MAXIMA_MS = 15000

// Celulares viejos (iOS 15 y anteriores) no tienen AbortSignal.timeout.
// Sin esta revisión, ahí cada petición fallaría como "sin conexión".
const limiteDeEspera = (): AbortSignal | undefined =>
  typeof AbortSignal.timeout === 'function'
    ? AbortSignal.timeout(ESPERA_MAXIMA_MS)
    : undefined

/** Saca el mensaje legible de lo que devolvió el servidor. */
function mensajeDe(cuerpo: unknown): string {
  const detalle = (cuerpo as { detail?: unknown } | null)?.detail
  if (typeof detalle === 'string') return detalle
  // Las validaciones de FastAPI llegan como lista; sin esto la pantalla
  // mostraba "[object Object]".
  if (Array.isArray(detalle) && detalle.length > 0) {
    const primero = detalle[0] as { msg?: string }
    if (primero?.msg) return primero.msg.replace(/^Value error, /, '')
  }
  return 'No se pudo completar. Intenta otra vez.'
}

async function pedir<T>(
  ruta: string,
  opciones: RequestInit = {},
  // Las peticiones de entrada no echan a nadie: el 401 de un login fallido
  // es "te equivocaste de clave", no "se te venció la sesión". Sin esto, la
  // pantalla se recarga y se lleva lo que la persona acababa de escribir.
  esEntrada = false,
): Promise<T> {
  const sesion = leerSesion()
  const signal = limiteDeEspera()

  let respuesta: Response
  try {
    respuesta = await fetch(`/api${ruta}`, {
      ...opciones,
      signal,
      headers: {
        'Content-Type': 'application/json',
        ...(sesion ? { Authorization: `Bearer ${sesion.access_token}` } : {}),
        ...opciones.headers,
      },
    })
  } catch {
    // fetch solo falla así cuando no hubo respuesta: sin red o sin servidor.
    // El mensaje del navegador ("Failed to fetch") viene en inglés.
    throw new SinConexion()
  }

  if (respuesta.status === 401 && !esEntrada) {
    borrarSesion()
    window.location.replace('/login')
    throw new ErrorApi('Tu sesión venció.', 401)
  }

  if (!respuesta.ok) {
    // El backend manda mensajes ya escritos para la gente del negocio;
    // se muestran tal cual en vez de inventar uno genérico.
    const cuerpo = await respuesta.json().catch(() => null)
    throw new ErrorApi(mensajeDe(cuerpo), respuesta.status)
  }

  if (respuesta.status === 204) return undefined as T
  return (await respuesta.json()) as T
}

export const api = {
  get: <T>(ruta: string) => pedir<T>(ruta),
  post: <T>(ruta: string, datos?: unknown) =>
    pedir<T>(ruta, { method: 'POST', body: JSON.stringify(datos ?? {}) }),
  patch: <T>(ruta: string, datos: unknown) =>
    pedir<T>(ruta, { method: 'PATCH', body: JSON.stringify(datos) }),
  put: <T>(ruta: string, datos: unknown) =>
    pedir<T>(ruta, { method: 'PUT', body: JSON.stringify(datos) }),
  borrar: <T>(ruta: string) => pedir<T>(ruta, { method: 'DELETE' }),
}

/** En `nombre` puede ir el nombre de usuario o el correo: el servidor busca
 *  por los dos. El código solo se manda cuando se entra como administrador. */
export async function entrar(
  nombre: string,
  clave: string,
  codigo?: string,
): Promise<Sesion> {
  const sesion = await pedir<Sesion>(
    '/auth/entrar',
    {
      method: 'POST',
      body: JSON.stringify({ nombre, clave, codigo: codigo || null }),
    },
    true,
  )
  guardarSesion(sesion)
  return sesion
}
