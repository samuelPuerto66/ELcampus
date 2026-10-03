# El Campus

Sistema de caja, inventario y pedidos para El Campus (Bar, Grill, Fun & Market).
Supermercado entre semana, restaurante los fines de semana.

Ver [`docs/plan.md`](docs/plan.md) para la arquitectura, el modelo de datos y el
plan de trabajo por fases (documento vivo).

## Cómo está armado

```
backend/     API en FastAPI + SQLite. Una sola fuente de verdad.
apps/web/    App en React. Las tres pantallas viven aquí:
             caja (PC), mesas (celular del mesero) y admin.
docs/        Plan técnico.
```

Las tres pantallas son **una sola aplicación web**. La caja no es una app
aparte: es el navegador en pantalla completa (modo kiosco) en el PC del
mostrador, hablando con el servidor por `localhost`. Un solo código, una sola
estética, y el lector de código de barras funciona igual porque se comporta
como un teclado.

> **Sobre las rutas de este archivo:** todos los comandos se corren parados en
> la carpeta del repositorio — la que contiene `backend/` y `apps/`. Cada
> bloque empieza desde ahí, así que funcionan sin importar dónde hayas
> clonado el proyecto.

## Instalarlo (solo la primera vez)

Recién clonado no existen `backend/.venv` ni `apps/web/node_modules`, así que
nada arranca hasta crearlos. Hace falta **Python 3.12** y **Node 20** o más
nuevos.

**1 · Dependencias del servidor**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**2 · Dependencias de la app web**

```powershell
cd apps\web
npm install
```

**3 · Crear la base con datos de prueba**

```powershell
cd backend
.\.venv\Scripts\python.exe seed.py
```

Crea tres usuarios de desarrollo — `admin`, `vendedor` y `mesero`, todos con
clave `campus123`. **Antes de usarlo en el negocio hay que crear los usuarios
reales y borrar estos.**

**4 · Poner el código de administrador** ← obligatorio

```powershell
cd backend
.\.venv\Scripts\python.exe codigo_admin.py
```

Las cuentas de administrador necesitan, además de su clave, un código
compartido entre los administradores. **Sin este paso nadie puede entrar como
admin:** el servidor responde "El código de administrador no está
configurado". El script lo pide por teclado (no se ve al escribir), lo pide
dos veces para confirmar, y guarda solo el hash en `backend/.codigo-admin`,
que está fuera del repositorio. Si se olvida, se vuelve a correr y se pone
uno nuevo.

Los vendedores y meseros no necesitan código: entran solo con nombre (o
correo) y clave.

## Levantarlo en desarrollo

Hacen falta **dos terminales** de PowerShell abiertas al tiempo, cada una
parada en la carpeta del repositorio. No hay que activar el entorno virtual:
los comandos llaman directo a su Python.

**Terminal 1 · Servidor**

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**Terminal 2 · App web**

```powershell
cd apps\web
npm run dev
```

Luego abre http://localhost:5173. La documentación de la API queda en
http://127.0.0.1:8000/docs.

> En Windows PowerShell 5.1 el `&&` no existe: cada comando va en su propia
> línea. Y si VS Code intenta activar el entorno virtual solo y sale un error
> de paréntesis, ignóralo — estos comandos no lo necesitan.

## Reglas sobre la plata

Estas no son detalles técnicos: son controles que protegen la caja, y
conviene que todo el equipo las conozca.

- **No se cobra sin abrir la caja.** Al entrar, el vendedor cuenta con cuánto
  empieza. Si no, esa plata no la contaría ningún cierre.
- **El cierre es a ciegas.** El sistema no muestra cuánto debería haber hasta
  después de que el vendedor escribe lo que contó. Si lo mostrara antes,
  nadie contaría de verdad.
- **Un vendedor solo deshace su propia última venta, y dentro de 10 minutos.**
  Para cualquier otra anulación se necesita un administrador. Cobrar en
  efectivo y anular un rato después es la forma más vieja de sacar plata de
  una caja sin que se note.
- **Las devoluciones salen del turno en que se hacen**, no del día de la
  venta original. Anular hoy algo de ayer descuenta del cajón de hoy, que es
  de donde sale la plata.
- **El precio se congela cuando el cliente pide.** Subir un precio con mesas
  abiertas no cambia lo que esas mesas van a pagar.

## Copias de seguridad

El servidor hace una copia al arrancar cada día, en `backend/respaldos/`, y
conserva 30 días. Para forzar una antes de algo riesgoso:

```powershell
cd backend
.\.venv\Scripts\python.exe respaldo.py
```

Esto guarda en el mismo computador: protege contra un borrado o un archivo
dañado, **no contra un robo o un incendio**. Vale la pena sincronizar la
carpeta `respaldos/` a una nube.

## La cocina

Hay un cuarto rol: **cocina**. Entra con su propio usuario y ve una sola
pantalla con los platos por preparar, agrupados por mesa y ordenados por
hora de llegada. Tocar un plato lo marca listo, y el mesero lo ve en su
celular al instante.

Los platos llegan a la cocina **cuando el mesero los envía**, no cuando el
cliente pide la cuenta. Las bebidas no aparecen: una cerveza no se cocina.

El borde de cada mesa cambia de color con la espera — amarillo, naranja a
los 10 minutos, rojo a los 20 — para que se vea de lejos qué está demorado.

## Cargar el inventario

Pestaña **Cargar** del panel de administrador. Se escanea un producto nuevo
y el sistema le pregunta el nombre a Open Food Facts para ahorrar tecleo;
si no lo conoce, se escribe a mano. Después de guardar, el cursor vuelve
solo al escáner para encadenar uno tras otro.

Que Open Food Facts no conozca un producto es lo normal con marcas locales,
no una falla. Y si no hay internet, la carga sigue funcionando igual: solo
deja de sugerir nombres.

## Recetas: que los platos descuenten inventario

Un **insumo** es algo que se controla en inventario pero no se vende suelto:
la carne, el chorizo. Se registra como cualquier producto, marcando la
casilla "es un insumo de cocina" — así no aparece en la caja ni en el menú
del mesero, y si alguien lo escanea el sistema avisa que no se vende.

La **receta** de un plato dice qué insumos lleva y cuánto. Se arma en la
pestaña Costos, en el botón *Receta* de cada plato. Desde que un plato
tiene receta pasan dos cosas:

- Venderlo **descuenta sus insumos** del inventario.
- Su **costo se calcula solo** y deja de ser un número a ojo. Si a algún
  insumo le falta el costo, el sistema dice que no sabe en vez de inventar
  una cifra.

Al anular una venta se devuelve al inventario **exactamente lo que salió**,
guiándose por los movimientos registrados y no por la receta de hoy: si la
receta cambió entre medias, el inventario igual queda bien.

## Costos y utilidad

En el panel del administrador, la pestaña **Costos** es donde se carga lo que
cuesta cada producto y cada plato. Mientras un producto no tenga costo, el
resumen del día avisa que la utilidad que muestra es mayor que la real.

## Después de traer cambios nuevos (`git pull`)

Si el esquema de la base cambió, la base que ya tienes en el disco **no se
actualiza sola**: `create_all` crea tablas nuevas pero no agrega columnas a
las que ya existen. Para ponerla al día sin perder lo que tiene dentro:

```powershell
cd backend
.\.venv\Scripts\python.exe migrar.py
```

Se puede correr las veces que haga falta: cada paso mira primero si ya está
hecho, y si no hay nada que cambiar lo dice y no toca nada. Si te saltas este
paso después de un cambio de esquema, la app falla al leer columnas que
todavía no existen.

Vale la pena correr también `pip install -r requirements.txt` y `npm install`
por si entraron dependencias nuevas.

## Pruebas

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

## En el negocio (producción)

```powershell
cd apps\web
npm run build
```

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Compilada, la app web la entrega el mismo servidor: un solo proceso y un solo
puerto. La caja abre `http://localhost:8000` y los celulares del salón entran
por la IP del PC. El administrador remoto entra por Tailscale, no por un
puerto abierto a internet.

## Si algo falla

**`WinError 10013` al levantar el servidor** — el puerto 8000 ya está ocupado,
casi siempre por otra instancia que quedó corriendo. Para ver quién lo tiene:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

**"El código de administrador no está configurado"** — falta el paso 4 de la
instalación.

**La app carga pero falla al entrar o al leer usuarios** — es probable que la
base esté desactualizada. Corre `migrar.py`.
