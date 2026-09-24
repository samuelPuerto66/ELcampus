import Brasas from './Brasas'

/** El brasero: tres manchas de luz muy difuminadas más las chispas subiendo.
 *  Va en una capa fija detrás de todo y no recibe clics, así que se puede
 *  poner en cualquier pantalla sin tocar su contenido. */
export default function Fondo() {
  return (
    <div className="ambiente" aria-hidden="true">
      <Brasas />
      <div className="aura aura-alta" />
      <div className="aura aura-centro" />
      <div className="aura aura-baja" />
    </div>
  )
}
