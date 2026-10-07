# El Campus

Sistema de caja, inventario y pedidos para El Campus (Bar, Grill, Fun & Market).
Supermercado entre semana, restaurante los fines de semana.

Ver [`docs/plan.md`](docs/plan.md) para la arquitectura, el modelo de datos y el
plan de trabajo por fases (documento vivo).

## Cómo está armado

```
backend/     API en FastAPI + SQLite. Una sola fuente de verdad.
apps/web/    App en React. Todas las pantallas viven aquí:
             caja (PC), mesas (celular del mesero), cocina y admin.
docs/        Plan técnico.
```

Todas las pantallas son **una sola aplicación web**. La caja no es una app
aparte: es el navegador en pantalla completa (modo kiosco) en el PC del
mostrador, hablando con el servidor por `localhost`. Un solo código, una sola
estética, y el lector de código de barras funciona igual porque se comporta
como un teclado.

> **Sobre las rutas de este archivo:** todos los comandos se corren parados en
> la carpeta del repositorio — la que contiene `backend/` y `apps/`. Cada
> bloque empieza desde ahí, así que funcionan sin importar dónde hayas
> clonado el proyecto.

## Prenderlo

Hace falta tener instalados **Python 3.12** y **Node 20**, o más nuevos. Con
eso, en **una sola terminal** parada en la carpeta del repositorio:

```powershell
npm start
```

Eso es todo, también recién clonado y después de cada `git pull`. El comando
hace en orden lo que antes eran varios pasos a mano, cada uno solo cuando
hace falta:

1. Revisa que no haya otro El Campus prendido.
2. Instala las dependencias de Python y de Node si faltan o si alguien
   agregó una nueva. La primera vez tarda unos minutos; después, segundos.
3. Si no hay base, la crea con datos de prueba. Si ya hay, la pone al día
   con `migrar.py`, sin borrar nada.
4. Si no hay código de administrador, pregunta si lo quieres poner.
5. Prende el servidor y la app web en esa misma terminal, abre el navegador
   y muestra la dirección para los celulares.

**Ctrl+C** apaga todo junto. Si cambias el código no hace falta reiniciar:
el servidor y la app se recargan solos.

Los usuarios de prueba son `admin`, `vendedor`, `mesero` y `cocina`, todos
con clave `campus123`. **Antes de usarlo en el negocio hay que crear los
usuarios reales y borrar estos.**

Todo lo que hace está en [`iniciar.mjs`](iniciar.mjs), explicado paso por
paso. Para prenderlo sin que abra el navegador: `npm start -- --sin-navegador`.

### El código de administrador

Las cuentas de administrador necesitan, además de su clave, un código
compartido entre los administradores. **Sin él nadie puede entrar como
admin:** el servidor responde "El código de administrador no está
configurado". `npm start` lo pregunta mientras falte. Para ponerlo o
cambiarlo aparte:

```powershell
cd backend
.\.venv\Scripts\python.exe codigo_admin.py
```

Lo pide por teclado (no se ve al escribir), dos veces para confirmar, y
guarda solo el hash en `backend/.codigo-admin`, que está fuera del
repositorio. Si se olvida, se vuelve a correr y se pone uno nuevo.

Los vendedores y meseros no necesitan código: entran solo con nombre (o
correo) y clave.

### Desde los celulares

Con el celular en el mismo WiFi que el PC, abre la dirección que `npm start`
muestra en "En los celulares" (algo como `http://192.168.1.20:5173`). La
primera vez, Windows puede preguntar si deja pasar a Node.js: dale permitir
en **redes privadas**, o el celular no carga.

### A mano, por partes

Si hace falta prender cada parte por su lado (por ejemplo, para ver el
registro completo del servidor, que `npm start` resume), son dos terminales:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
cd apps\web
npm run dev
```

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
- **La caja no cobra una mesa que cambió.** Si el mesero agrega algo
  mientras el cajero le lee la cuenta al cliente, la caja lo muestra y el
  servidor no deja cobrar la cifra vieja.
- **Pagos divididos.** Mitad efectivo y mitad Nequi se registra como dos
  pagos que tienen que sumar exacto la cuenta. El cierre de caja solo
  espera la parte en efectivo.
- **La propina es de los empleados.** Se registra aparte: no cuenta como
  venta ni como utilidad, pero si la dan en efectivo sí está en el cajón.
  Es voluntaria, así que la caja nunca la pone sola: el cajero pregunta.
- **Todo descuento lleva motivo.** Hasta el 10% de la cuenta lo da el
  vendedor solo; más que eso, o una cortesía completa, necesita el código de
  un administrador. El dueño ve cada descuento y cada anulación en el
  resumen, con quién lo hizo y por qué.
- **Las cifras se escriben como siempre.** "350.000" son trescientos
  cincuenta mil. Antes el sistema lo leía como 350, y un cierre de caja
  podía reportar un faltante que no existía.

## Copias de seguridad

El servidor hace una copia al arrancar cada día, en `backend/respaldos/`, y
conserva 30 días. Para forzar una antes de algo riesgoso:

```powershell
cd backend
.\.venv\Scripts\python.exe respaldo.py
```

Mientras el servidor esté prendido, revisa cada hora si ya está la copia
del día; así hay copia diaria aunque el PC pase semanas sin apagarse.

La copia a mano lleva la hora en el nombre (`elcampus-2026-10-06-182700.db`)
para no pisar la copia automática del día: si alguien la hace cuando el daño
ya está hecho, la copia buena de la mañana sigue ahí.

Esto guarda en el mismo computador: protege contra un borrado o un archivo
dañado, **no contra un robo o un incendio**. Vale la pena sincronizar la
carpeta `respaldos/` a una nube.

## Si se cae el WiFi del local

El mesero puede seguir trabajando. Lo que confirma queda guardado en el
celular y aparece en naranja como "Esperando señal"; cuando vuelve la red se
envía solo, sin que nadie toque nada. Cada pedido lleva su propia clave, así
que si la señal se corta justo después de enviarlo y el celular lo reintenta,
el servidor lo reconoce y no lo cuenta dos veces.

El menú también queda guardado en el celular, así que una mesa se puede
atender aunque se abra sin señal. Lo único que no funciona sin red es
pedir la cuenta: la caja tiene que estar enterada.

Si la caja rechaza un pedido (por ejemplo, un plato que ya no existe), el
mesero lo ve en rojo en esa mesa y puede volver a anotarlo o descartarlo.

## La cocina

Hay un cuarto rol: **cocina**. Entra con su propio usuario y ve una sola
pantalla con los platos por preparar, agrupados por mesa y ordenados por
hora de llegada. Tocar un plato lo marca listo, y el mesero lo ve en su
celular al instante.

Los platos llegan a la cocina **cuando el mesero los envía**, no cuando el
cliente pide la cuenta. Las bebidas no aparecen: una cerveza no se cocina.

El borde de cada mesa cambia de color con la espera — amarillo, naranja a
los 10 minutos, rojo a los 20 — para que se vea de lejos qué está demorado.

**Notas para la cocina.** Cada plato anotado tiene un botón "+ Nota" con
las más comunes a un toque ("Sin cebolla", "Bien asado"). Si la línea tiene
varios platos, el mesero escoge si la nota es para todos o "solo para 1":
así quedan "dos picadas, una sin cebolla". La lista de notas rápidas está
en `NotaDelPlato.tsx`.

## Corregir lo que ya se envió

Si el mesero mandó 3 cervezas y eran 2, toca **Corregir** en esa línea,
escoge cuántas quitar y por qué. Las reglas son las mismas que para anular
una venta:

- **Lo propio y recién enviado** (menos de 5 minutos) se corrige solo.
- **Lo que envió otra persona, lo que lleva más rato, o un plato que la
  cocina ya preparó**, necesita el código de un administrador.
- **Siempre queda escrito**: qué, cuánto, de qué mesa, quién y por qué. El
  dueño lo ve en "Para revisar hoy".

La caja también puede corregir la mesa que está cobrando, con el mismo
diálogo. No hay ninguna otra forma de bajar la cuenta de una mesa.

## Platos para llevar

En la caja, el botón **Platos** muestra el menú para vender sin abrir una
mesa. Al cobrar, los platos van solos a la cocina como "Para llevar", con
el nombre del cliente si se escribió, y cuando la cocina los marca listos
la caja avisa a quién hay que llamar. Si se anula la venta, la cocina deja
de verlos.

## Fiado

El cuaderno de fiados del negocio, en la pestaña **Fiado** del
administrador y en el botón **Fiados** de la caja.

- **A quién se le fía lo decide el dueño.** Solo el administrador registra
  clientes y les pone cupo (hasta cuánto pueden deber). Sin cupo no hay
  límite; lo prudente es ponerle uno.
- **Vender fiado** es cobrar en la caja con "Fiado" como forma de pago y
  escoger al cliente. También se puede pagar una parte y fiar el resto, con
  el pago dividido. La caja no deja pasar del cupo.
- **Los abonos** se reciben en la caja. Si son en efectivo entran al cuadre
  del turno, igual que una venta. Un abono mal registrado solo lo anula un
  administrador.
- **Lo que debe cada cliente no se guarda: se calcula** sumando lo fiado y
  restando lo abonado. Si se anula una venta fiada, la deuda baja sola.

El resumen del día muestra lo fiado hoy, lo abonado hoy y cuánto le deben
al negocio en total. Lo fiado no aparece en "Cómo entró la plata", porque
no entró.

## Facturación electrónica

Todavía no está programada, a propósito: antes hay que saber si el negocio
está obligado y cómo. Las preguntas para el contador y lo que cambiaría en
el sistema están en [`docs/facturacion-dian.md`](docs/facturacion-dian.md).

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

`npm start` ya lo hace solo: instala las dependencias nuevas y pone la base
al día. Lo de abajo es por si hace falta entenderlo o hacerlo a mano.

Si el esquema de la base cambió, la base que ya tienes en el disco **no se
actualiza sola**: `create_all` crea tablas nuevas pero no agrega columnas a
las que ya existen. Para eso está `migrar.py`, que la pone al día sin perder
lo que tiene dentro:

```powershell
cd backend
.\.venv\Scripts\python.exe migrar.py
```

Se puede correr las veces que haga falta: cada paso mira primero si ya está
hecho, y si no hay nada que cambiar lo dice y no toca nada. Si la base no se
pone al día después de un cambio de esquema, la app falla al leer columnas
que todavía no existen.

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

**"El puerto 8000 ya está ocupado"** (o `WinError 10013`, o el 5173) — casi
siempre es otro El Campus que quedó prendido en otra terminal: apágalo allá
con Ctrl+C. Para ver quién tiene el puerto:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

**`npm start` dice que la ejecución de scripts está deshabilitada** — es
PowerShell bloqueando a npm, no un problema del proyecto. Corre lo mismo sin
pasar por npm:

```powershell
node iniciar.mjs
```

**El celular no carga la página** — revisa que esté en el mismo WiFi que el
PC y que Windows deje pasar a Node.js en redes privadas (Firewall de Windows
→ Permitir una aplicación).

**"El código de administrador no está configurado"** — falta ponerlo: vuelve
a correr `npm start` y responde que sí cuando lo pregunte (ver "El código de
administrador", arriba).

**La app carga pero falla al entrar o al leer usuarios** — es probable que la
base esté desactualizada. Apaga y vuelve a correr `npm start`, que la pone al
día; si sigue fallando, mira el error que muestra `migrar.py` al arrancar.
