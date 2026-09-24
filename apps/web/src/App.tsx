import { Navigate, Route, Routes } from 'react-router-dom'

import type { Rol } from './api/tipos'
import Admin from './pantallas/Admin'
import Caja from './pantallas/Caja'
import Login from './pantallas/Login'
import Mesa from './pantallas/Mesa'
import Mesas from './pantallas/Mesas'
import { pantallaDe, useSesion } from './sesion'

function Protegida({ roles, children }: { roles: Rol[]; children: React.ReactNode }) {
  const { sesion } = useSesion()

  if (!sesion) return <Navigate to="/login" replace />
  if (sesion.rol !== 'administrador' && !roles.includes(sesion.rol)) {
    return <Navigate to={pantallaDe(sesion.rol)} replace />
  }
  return <>{children}</>
}

export default function App() {
  const { sesion } = useSesion()

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/caja"
        element={
          <Protegida roles={['vendedor']}>
            <Caja />
          </Protegida>
        }
      />
      <Route
        path="/mesas"
        element={
          <Protegida roles={['mesero', 'vendedor']}>
            <Mesas />
          </Protegida>
        }
      />
      <Route
        path="/mesa/:numero"
        element={
          <Protegida roles={['mesero', 'vendedor']}>
            <Mesa />
          </Protegida>
        }
      />
      <Route
        path="/admin"
        element={
          <Protegida roles={[]}>
            <Admin />
          </Protegida>
        }
      />
      <Route
        path="*"
        element={<Navigate to={sesion ? pantallaDe(sesion.rol) : '/login'} replace />}
      />
    </Routes>
  )
}
