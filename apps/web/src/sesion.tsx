import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

import { borrarSesion, leerSesion } from './api/cliente'
import type { Rol, Sesion } from './api/tipos'

interface Contexto {
  sesion: Sesion | null
  entrar: (sesion: Sesion) => void
  salir: () => void
}

const ContextoSesion = createContext<Contexto | null>(null)

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(() => leerSesion())

  const valor = useMemo<Contexto>(
    () => ({
      sesion,
      entrar: setSesion,
      salir: () => {
        borrarSesion()
        setSesion(null)
      },
    }),
    [sesion],
  )

  return <ContextoSesion.Provider value={valor}>{children}</ContextoSesion.Provider>
}

export function useSesion() {
  const contexto = useContext(ContextoSesion)
  if (!contexto) throw new Error('useSesion se usó fuera del ProveedorSesion')
  return contexto
}

/** A dónde va cada quien al entrar. */
export function pantallaDe(rol: Rol): string {
  if (rol === 'mesero') return '/mesas'
  if (rol === 'cocina') return '/cocina'
  if (rol === 'administrador') return '/admin'
  return '/caja'
}
