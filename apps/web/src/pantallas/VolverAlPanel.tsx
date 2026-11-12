import { Link } from 'react-router-dom'

import { useSesion } from '../sesion'

/**
 * Botón para regresar al panel de administración.
 *
 * El administrador puede entrar a la caja, a las mesas y a la cocina para
 * revisar o echar una mano. Sin esto quedaba encerrado allá: la única salida
 * era cerrar sesión y volver a entrar con su clave y su código.
 *
 * No le sale a nadie más. Al vendedor, al mesero y a la cocina no les
 * aparece porque no tienen panel al que volver —y aunque forzaran la
 * dirección, el guardia de App.tsx los devuelve a su pantalla—.
 */
export default function VolverAlPanel() {
  const { sesion } = useSesion()
  if (sesion?.rol !== 'administrador') return null

  return (
    <Link className="volver-panel" to="/admin">
      ← Administración
    </Link>
  )
}
