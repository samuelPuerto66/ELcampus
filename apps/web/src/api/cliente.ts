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

export class ErrorApi extends Error {}

async function pedir<T>(
  ruta: string,
  opciones: RequestInit = {},
  // Las peticiones de entrada no echan a nadie: el 401 de un login fallido
  // es "te equivocaste de clave", no "se te venció la sesión". Sin esto, la
  // pantalla se recarga y se lleva lo que la persona acababa de escribir.
  esEntrada = false,
): Promise<T> {
  const sesion = leerSesion()

  const respuesta = await fetch(`/api${ruta}`, {
    ...opciones,
    headers: {
      'Content-Type': 'application/json',
      ...(sesion ? { Authorization: `Bearer ${sesion.access_token}` } : {}),
      ...opciones.headers,
    },
  })

  if (respuesta.status === 401 && !esEntrada) {
    borrarSesion()
    window.location.replace('/login')
    throw new ErrorApi('Tu sesión venció.')
  }

  if (!respuesta.ok) {
    // El backend manda mensajes ya escritos para la gente del negocio;
    // se muestran tal cual en vez de inventar uno genérico.
    const cuerpo = await respuesta.json().catch(() => null)
    throw new ErrorApi(cuerpo?.detail ?? 'No se pudo completar. Intenta otra vez.')
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
