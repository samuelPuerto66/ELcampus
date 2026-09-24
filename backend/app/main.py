import jwt
from fastapi import APIRouter, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as ErrorDeStarlette

from .auth import leer_token
from .config import WEB_DIST
from .database import Base, engine
from .eventos import tablero
from .routers import auth, caja, inventario, pedidos, platos, productos, reportes, ventas

# Dev: crea las tablas si no existen. Las migraciones de Alembic mandan
# cuando el esquema cambia con datos ya cargados.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="El Campus API", version="0.2.0")

# En producción el mismo servidor entrega la app web, así que no hay origen
# cruzado. Esto es solo para el servidor de desarrollo de Vite.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def control_de_cache(request: Request, call_next):
    """Que una versión nueva llegue sin que nadie tenga que recargar a la fuerza.

    Los archivos de /assets llevan un hash en el nombre: cambian de nombre
    cuando cambia su contenido, así que se pueden guardar para siempre. El
    index.html no, y es el que dice cuáles assets cargar — si el navegador
    se lo queda, la caja y los celulares siguen corriendo la versión vieja
    después de publicar un arreglo.
    """
    respuesta = await call_next(request)
    ruta = request.url.path
    if ruta.startswith("/assets/") or ruta.startswith("/fuentes/"):
        respuesta.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif not ruta.startswith("/api"):
        respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


api = APIRouter(prefix="/api")
api.include_router(auth.router)
api.include_router(productos.router)
api.include_router(platos.router)
api.include_router(ventas.router)
api.include_router(pedidos.router)
api.include_router(inventario.router)
api.include_router(caja.router)
api.include_router(reportes.router)


@api.get("/salud", tags=["sistema"])
def salud():
    return {"estado": "ok"}


app.include_router(api)


@app.websocket("/api/eventos")
async def eventos(websocket: WebSocket, token: str = ""):
    """Canal en vivo hacia la caja.

    El navegador no puede mandar encabezados al abrir un WebSocket, así que
    el token viaja como parámetro. Va por la red local del negocio.
    """
    try:
        leer_token(token)
    except jwt.PyJWTError:
        await websocket.close(code=1008)
        return

    await tablero.conectar(websocket)
    try:
        while True:
            # No esperamos mensajes del cliente; esto mantiene viva la
            # conexión y detecta cuándo se cierra.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await tablero.desconectar(websocket)


# La app web compilada se sirve desde el mismo servidor: un solo proceso,
# un solo puerto. La caja abre localhost y los celulares la IP del PC.
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    @app.exception_handler(ErrorDeStarlette)
    async def entregar_index_en_rutas_de_react(request: Request, exc: ErrorDeStarlette):
        """React Router maneja /login, /caja, /mesas, etc. en el navegador,
        pero StaticFiles solo conoce archivos reales: si alguien recarga la
        página o abre un acceso directo a esas rutas, sin esto el servidor
        respondería 404 en vez de entregar la app.
        """
        si_no_es_de_la_api = not request.url.path.startswith("/api")
        if exc.status_code == 404 and si_no_es_de_la_api:
            return FileResponse(WEB_DIST / "index.html")
        # Cualquier otro caso (401, 403, un 404 real de /api) sigue el
        # comportamiento normal de FastAPI en vez de tumbar la respuesta.
        return await http_exception_handler(request, exc)
