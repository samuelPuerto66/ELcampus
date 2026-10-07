/**
 * Prende El Campus completo con un solo comando, desde la raíz del proyecto:
 *
 *     npm start
 *
 * Antes eran dos terminales y varios pasos que había que recordar. Este
 * archivo los hace en orden, y cada uno solo cuando hace falta:
 *
 *   1. Revisa que no haya otro El Campus prendido (puertos 8000 y 5173).
 *   2. Instala las dependencias de Python y de Node si faltan o cambiaron.
 *   3. Crea la base con datos de prueba si no existe; si ya existe, la pone
 *      al día con migrar.py.
 *   4. Si no hay código de administrador, ofrece ponerlo.
 *   5. Prende el servidor y la app web en esta misma terminal, abre el
 *      navegador y muestra la dirección para los celulares.
 *
 * Ctrl+C apaga todo junto.
 *
 * Es para desarrollo y pruebas. En el negocio se usa la app compilada, que
 * la entrega el mismo servidor (ver "En el negocio" en el README).
 *
 * Opción: `npm start -- --sin-navegador` prende todo sin abrir el navegador.
 */

import { spawn, spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createSocket } from 'node:dgram'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { connect } from 'node:net'
import { dirname, join } from 'node:path'
import { createInterface } from 'node:readline'
import { fileURLToPath } from 'node:url'

// --- Dónde está cada cosa ----------------------------------------------------

const RAIZ = dirname(fileURLToPath(import.meta.url))
const BACKEND = join(RAIZ, 'backend')
const WEB = join(RAIZ, 'apps', 'web')

const EN_WINDOWS = process.platform === 'win32'
const PYTHON = EN_WINDOWS
  ? join(BACKEND, '.venv', 'Scripts', 'python.exe')
  : join(BACKEND, '.venv', 'bin', 'python')
const VITE = join(WEB, 'node_modules', 'vite', 'bin', 'vite.js')

const PUERTO_API = 8000
// El mismo de apps/web/vite.config.ts, que ya le pasa al 8000 todo lo de /api.
const PUERTO_WEB = 5173

const ABRIR_NAVEGADOR = !process.argv.includes('--sin-navegador')

// Python en UTF-8 y sin guardarse lo que imprime: si no, las tildes salen
// dañadas y los mensajes del servidor llegan tarde a la terminal.
const ENTORNO = { ...process.env, PYTHONUTF8: '1', PYTHONUNBUFFERED: '1' }

// --- Mensajes en la terminal -------------------------------------------------

const CON_COLOR = process.stdout.isTTY && !process.env.NO_COLOR
const pintar = (codigo) => (texto) => (CON_COLOR ? `\x1b[${codigo}m${texto}\x1b[0m` : texto)
const verde = pintar(32)
const amarillo = pintar(33)
const rojo = pintar(31)
const azul = pintar(36)
const morado = pintar(35)
const gris = pintar(90)

const paso = (texto) => console.log(`${azul('›')} ${texto}`)
const aviso = (texto) => console.log(`${amarillo('!')} ${texto}`)

/** Para antes de prender nada: explica qué pasó y sale. */
function fallar(texto) {
  console.error(`\n${rojo('✖')} ${texto}\n`)
  process.exit(1)
}

// --- Utilidades --------------------------------------------------------------

/** Corre un comando hasta que termine, con lo que imprime a la vista. */
function correr(comando, args, { cwd, shell = false }) {
  return spawnSync(comando, args, { cwd, env: ENTORNO, stdio: 'inherit', shell }).status === 0
}

/** Huella del contenido de un archivo: si el archivo cambia, cambia la huella. */
const huella = (archivo) => createHash('sha256').update(readFileSync(archivo)).digest('hex')

const leer = (archivo) => (existsSync(archivo) ? readFileSync(archivo, 'utf8') : '')

const pausa = (ms) => new Promise((listo) => setTimeout(listo, ms))

// --- 1. Que no haya otro El Campus prendido ----------------------------------

/** true si algo ya está escuchando en ese puerto de este PC. */
function puertoOcupado(puerto) {
  return new Promise((responder) => {
    const prueba = connect(puerto, '127.0.0.1')
    prueba.once('connect', () => {
      prueba.destroy()
      responder(true)
    })
    prueba.once('error', () => responder(false))
  })
}

async function revisarPuertos() {
  for (const puerto of [PUERTO_API, PUERTO_WEB]) {
    if (await puertoOcupado(puerto)) {
      fallar(
        `El puerto ${puerto} ya está ocupado: lo más seguro es que El Campus siga prendido en ` +
          `otra terminal. Apágalo allá con Ctrl+C y vuelve a correr npm start.` +
          (EN_WINDOWS
            ? `\n  Para ver qué lo tiene ocupado: Get-NetTCPConnection -LocalPort ${puerto} -State Listen`
            : ''),
      )
    }
  }
}

// --- 2. Dependencias -----------------------------------------------------------
//
// Cada instalación deja una marca con la huella del archivo de dependencias
// con el que se hizo. Si alguien agrega una dependencia y haces git pull, la
// huella ya no coincide y se instala sola; si nada cambió, no se pierde tiempo.

function prepararPython() {
  if (!existsSync(PYTHON)) {
    paso('Creando el entorno de Python (esto pasa solo la primera vez)…')
    if (!crearEntornoPython()) {
      fallar(
        'No se pudo crear el entorno de Python. Instala Python 3.12 o más nuevo desde ' +
          'python.org (marcando "Add python.exe to PATH") y vuelve a intentar.',
      )
    }
  }

  const requisitos = join(BACKEND, 'requirements.txt')
  const marca = join(BACKEND, '.venv', '.requisitos-instalados')
  if (leer(marca) === huella(requisitos)) return

  paso('Instalando las dependencias del servidor…')
  const instalado = correr(
    PYTHON,
    ['-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', '-r', 'requirements.txt'],
    { cwd: BACKEND },
  )
  if (!instalado) {
    fallar('No se pudieron instalar las dependencias del servidor. Revisa el error de arriba (¿hay internet?).')
  }
  writeFileSync(marca, huella(requisitos))
}

function crearEntornoPython() {
  // En Windows primero "py", el lanzador oficial: "python" a secas a veces
  // es el atajo de la Microsoft Store, que no instala nada.
  const candidatos = EN_WINDOWS ? [['py', ['-3']], ['python', []]] : [['python3', []]]
  return candidatos.some(
    ([comando, previos]) =>
      correr(comando, [...previos, '-m', 'venv', '.venv'], { cwd: BACKEND }) && existsSync(PYTHON),
  )
}

function prepararWeb() {
  const candado = join(WEB, 'package-lock.json')
  const marca = join(WEB, 'node_modules', '.dependencias-instaladas')
  if (existsSync(VITE) && leer(marca) === huella(candado)) return

  paso('Instalando las dependencias de la app web…')
  // Con shell porque en Windows npm es un .cmd. Va como un solo texto, sin
  // lista de argumentos, que es la forma segura de hacerlo con shell. Sin
  // la auditoría ni los avisos de donaciones: eso se revisa aparte, con calma.
  if (!correr('npm install --no-audit --no-fund', [], { cwd: WEB, shell: true })) {
    fallar('No se pudieron instalar las dependencias de la app web. Revisa el error de arriba (¿hay internet?).')
  }
  // La huella se toma después: npm puede retocar el package-lock al instalar.
  writeFileSync(marca, huella(candado))
}

// --- 3. La base de datos -------------------------------------------------------

function prepararBase() {
  if (!existsSync(join(BACKEND, 'elcampus.db'))) {
    paso('No hay base todavía: creándola con datos de prueba…')
    if (!correr(PYTHON, ['seed.py'], { cwd: BACKEND })) {
      fallar('No se pudo crear la base. Revisa el error de arriba.')
    }
    return
  }

  // migrar.py revisa cada cambio antes de hacerlo: si la base ya está al
  // día, no toca nada. Así nadie tiene que acordarse de correrlo tras un pull.
  paso('Revisando que la base esté al día…')
  if (!correr(PYTHON, ['migrar.py'], { cwd: BACKEND })) {
    fallar(
      'migrar.py falló y la base no quedó al día. No se prende el servidor con la base ' +
        'a medias: revisa el error de arriba.',
    )
  }
}

// --- 4. El código de administrador --------------------------------------------

function revisarCodigoAdmin() {
  if (existsSync(join(BACKEND, '.codigo-admin'))) return

  // Sin teclado (por ejemplo, si lo prende otro programa) no hay a quién preguntarle.
  if (!process.stdin.isTTY) {
    aviso('Todavía no hay código de administrador: sin él nadie puede entrar como admin.')
    return
  }

  // La pregunta la hace el mismo codigo_admin.py y no este archivo: en
  // Windows, si dos programas leen el teclado uno detrás del otro, se pueden
  // robar las teclas.
  if (!correr(PYTHON, ['codigo_admin.py', '--si-falta'], { cwd: BACKEND })) {
    aviso('No se guardó el código. La próxima vez que corras npm start te lo vuelvo a preguntar.')
  }
}

// --- 5. Prender, avisar y apagar ----------------------------------------------

const procesos = []
let apagando = false

/** Prende un programa y muestra lo que imprime con su etiqueta adelante. */
function prender({ nombre, etiqueta, comando, args, cwd }) {
  const hijo = spawn(comando, args, { cwd, env: ENTORNO, stdio: ['ignore', 'pipe', 'pipe'] })

  for (const salida of [hijo.stdout, hijo.stderr]) {
    createInterface({ input: salida }).on('line', (linea) => console.log(`${etiqueta} ${linea}`))
  }

  hijo.on('error', (error) => {
    console.error(`\n${rojo('✖')} No se pudo prender ${nombre}: ${error.message}`)
    void apagar(1)
  })

  hijo.on('exit', () => {
    // Con Ctrl+C la terminal les avisa a todos al tiempo, y a veces ellos
    // cierran antes de que este proceso se entere: se espera un momento
    // para no confundir eso con una caída.
    setTimeout(() => {
      if (apagando) return
      console.error(`\n${rojo('✖')} ${nombre} se apagó de repente. El error debe estar justo arriba.`)
      void apagar(1)
    }, 500)
  })

  procesos.push(hijo)
}

const sigueVivo = (hijo) => hijo.exitCode === null && hijo.signalCode === null

const cuandoTermine = (hijo) =>
  sigueVivo(hijo) ? new Promise((listo) => hijo.once('exit', listo)) : Promise.resolve()

/** Corta un programa y todo lo que él haya prendido (el servidor tiene un hijo que recarga). */
function cortar(hijo) {
  if (EN_WINDOWS) {
    spawnSync('taskkill', ['/pid', String(hijo.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    hijo.kill('SIGKILL')
  }
}

async function apagar(codigo) {
  if (apagando) return
  apagando = true
  console.log(`\n${gris('Apagando El Campus…')}`)

  // Primero se les pide cerrar bien (con Ctrl+C la terminal ya se lo pidió)
  // y se les da un momento; al que no haya cerrado, se le corta.
  if (!EN_WINDOWS) procesos.filter(sigueVivo).forEach((hijo) => hijo.kill('SIGTERM'))
  await Promise.race([Promise.all(procesos.map(cuandoTermine)), pausa(3000)])
  procesos.filter(sigueVivo).forEach(cortar)

  console.log(gris('Listo, todo apagado.'))
  process.exit(codigo)
}

/** Espera a que una dirección conteste. false si pasa un minuto y nada. */
async function esperarA(url) {
  for (let intento = 0; intento < 120 && !apagando; intento++) {
    try {
      await fetch(url, { signal: AbortSignal.timeout(2000) })
      return true
    } catch {
      await pausa(500)
    }
  }
  return false
}

/**
 * La IP de este PC en la red del local: por ahí entran los celulares.
 *
 * Un PC puede tener varias (VirtualBox, WSL, una VPN…). "Conectar" un socket
 * UDP no manda nada por la red: solo le pregunta al sistema por cuál
 * adaptador saldría, y ese es el WiFi o el cable de verdad.
 */
function ipDelPc() {
  return new Promise((responder) => {
    const socket = createSocket('udp4')
    socket.on('error', () => {
      socket.close()
      responder(null)
    })
    socket.connect(53, '8.8.8.8', () => {
      const { address } = socket.address()
      socket.close()
      responder(address)
    })
  })
}

async function anunciar() {
  const ip = await ipDelPc()
  const celulares = ip
    ? `http://${ip}:${PUERTO_WEB}  (en el mismo WiFi)`
    : 'no encontré la red: revisa que este PC esté conectado al WiFi del local'
  const raya = gris('─'.repeat(64))

  console.log(
    [
      '',
      raya,
      `  ${verde('✔ El Campus está prendido')}`,
      '',
      `  En este PC:          http://localhost:${PUERTO_WEB}`,
      `  En los celulares:    ${celulares}`,
      `  Documentación API:   http://127.0.0.1:${PUERTO_API}/docs`,
      '',
      `  Usuarios de prueba:  admin · vendedor · mesero · cocina  (clave campus123)`,
      `  Para apagar todo:    Ctrl+C`,
      raya,
      '',
    ].join('\n'),
  )
}

function abrirNavegador(url) {
  const [comando, args] = EN_WINDOWS
    ? ['cmd', ['/c', 'start', '', url]]
    : [process.platform === 'darwin' ? 'open' : 'xdg-open', [url]]
  spawn(comando, args, { stdio: 'ignore', detached: true }).on('error', () => {}).unref()
}

// --- En orden ------------------------------------------------------------------

await revisarPuertos()
prepararPython()
prepararWeb()
prepararBase()
revisarCodigoAdmin()

paso('Prendiendo el servidor y la app web…\n')
process.on('SIGINT', () => void apagar(0))
process.on('SIGTERM', () => void apagar(0))

prender({
  nombre: 'El servidor',
  etiqueta: azul('api │'),
  comando: PYTHON,
  // Solo avisos y errores: lo de rutina (cada consulta, y la cocina pregunta
  // cada 20 s) llenaría la terminal y taparía lo importante. Los errores, y
  // el aviso de que recargó tras un cambio en el código, se siguen viendo.
  args: ['-m', 'uvicorn', 'app.main:app', '--reload', '--port', String(PUERTO_API), '--log-level', 'warning'],
  cwd: BACKEND,
})
prender({
  nombre: 'La app web',
  etiqueta: morado('web │'),
  comando: process.execPath,
  // --strictPort: si el puerto se ocupa, que avise en vez de irse a otro
  // distinto del que se anuncia abajo. --logLevel warn: las direcciones las
  // anuncia este archivo; Vite listaría también las de adaptadores virtuales.
  args: [VITE, '--port', String(PUERTO_WEB), '--strictPort', '--logLevel', 'warn'],
  cwd: WEB,
})

const listos = await Promise.all([
  esperarA(`http://127.0.0.1:${PUERTO_API}/api/salud`),
  esperarA(`http://127.0.0.1:${PUERTO_WEB}/`),
])
if (listos.every(Boolean)) {
  await anunciar()
  if (ABRIR_NAVEGADOR) abrirNavegador(`http://localhost:${PUERTO_WEB}`)
} else if (!apagando) {
  aviso('El servidor o la app web están tardando más de lo normal en prender. Revisa los mensajes de arriba.')
}
