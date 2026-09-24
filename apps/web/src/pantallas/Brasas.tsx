import { useEffect, useRef } from 'react'

/** Brasas subiendo en canvas: cada chispa nace abajo, sube oscilando, se
 *  enciende, y se apaga al llegar al tercio de arriba. El color sale de las
 *  variables del tema, así que si cambia el acento, cambian las brasas. */

interface Chispa {
  x: number
  y: number
  radio: number
  velocidad: number
  deriva: number
  vaiven: number
  angulo: number
  opacidad: number
  opacidadTope: number
  encendiendo: boolean
  color: [number, number, number]
}

function aRgb(css: string): [number, number, number] {
  const hex = css.trim().replace('#', '')
  const completo = hex.length === 3 ? hex.replace(/./g, (c) => c + c) : hex
  const n = Number.parseInt(completo, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

export default function Brasas() {
  const lienzo = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = lienzo.current
    if (!canvas) return

    // Quien pidió menos movimiento en su sistema no ve brasas moviéndose.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const estilo = getComputedStyle(document.documentElement)
    const colores: [number, number, number][] = [
      aRgb(estilo.getPropertyValue('--neon-brasa') || '#ff5e00'),
      aRgb(estilo.getPropertyValue('--neon-calido') || '#ffaa00'),
      aRgb(estilo.getPropertyValue('--neon') || '#ffc700'),
    ]

    let ancho = 0
    let alto = 0
    let chispas: Chispa[] = []

    function nacer(y?: number): Chispa {
      return {
        x: Math.random() * ancho,
        y: y ?? alto + Math.random() * 40,
        radio: Math.random() * 3.5 + 1.8,
        velocidad: Math.random() * 1.1 + 0.55,
        deriva: (Math.random() - 0.5) * 0.7,
        vaiven: Math.random() * 0.025 + 0.01,
        angulo: Math.random() * Math.PI * 2,
        opacidad: 0,
        opacidadTope: Math.random() * 0.55 + 0.35,
        encendiendo: true,
        color: colores[Math.floor(Math.random() * colores.length)],
      }
    }

    function medir() {
      const canvas = lienzo.current
      if (!canvas) return
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      ancho = canvas.clientWidth
      alto = canvas.clientHeight
      canvas.width = Math.round(ancho * dpr)
      canvas.height = Math.round(alto * dpr)
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)

      // La cantidad sale del área: en el PC de la caja se llena, en el
      // celular de un mesero salen pocas y no le come la batería.
      const cuantas = Math.min(65, Math.floor((ancho * alto) / 18000))
      chispas = Array.from({ length: cuantas }, () => nacer(Math.random() * alto))
    }

    medir()
    window.addEventListener('resize', medir)

    let cuadro = 0
    function pintar() {
      ctx!.clearRect(0, 0, ancho, alto)

      for (let i = 0; i < chispas.length; i++) {
        const c = chispas[i]

        c.y -= c.velocidad
        c.angulo += c.vaiven
        c.x += Math.sin(c.angulo) * 0.65 + c.deriva

        if (c.encendiendo) {
          c.opacidad += 0.018
          if (c.opacidad >= c.opacidadTope) c.encendiendo = false
        } else if (c.y < alto * 0.22) {
          c.opacidad -= 0.012
        }

        if (c.y < -15 || c.opacidad <= 0) {
          chispas[i] = nacer()
          continue
        }

        const alfa = Math.max(0, Math.min(c.opacidad, c.opacidadTope))
        const [r, g, b] = c.color

        ctx!.save()
        ctx!.shadowBlur = c.radio * 3.5
        ctx!.shadowColor = `rgba(${r}, ${g}, ${b}, ${alfa * 0.9})`

        ctx!.beginPath()
        ctx!.arc(c.x, c.y, c.radio, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(${r}, ${g}, ${b}, ${alfa})`
        ctx!.fill()

        // Corazón claro: es lo que la hace leer como chispa y no como punto.
        ctx!.beginPath()
        ctx!.arc(c.x, c.y, c.radio * 0.45, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(255, 255, 220, ${alfa * 0.75})`
        ctx!.fill()
        ctx!.restore()
      }

      cuadro = requestAnimationFrame(pintar)
    }

    cuadro = requestAnimationFrame(pintar)

    return () => {
      cancelAnimationFrame(cuadro)
      window.removeEventListener('resize', medir)
    }
  }, [])

  return <canvas ref={lienzo} className="brasas" aria-hidden="true" />
}
