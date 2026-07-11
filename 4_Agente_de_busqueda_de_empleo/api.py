"""
Artefacto 4 · Agente de búsqueda de empleo
La API HTTP (Fase 4): envuelve el motor del agente en un servicio web,
protegido por un TOKEN personal.

Mismo esqueleto que el api.py del Artefacto 2 (RAG):
  · lifespan       — prepara el motor UNA vez, al arrancar el servidor.
  · GET  /salud    — sin token: para comprobar que está vivo.
  · POST /preguntar — con X-Token: valida contra APP_TOKEN o devuelve 401.
  · GET  /         — sirve el frontend (cuando exista, en la Fase 6).

El motor (agente.py) no se toca: la API es solo otra INTERFAZ, como el CLI.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agente import procesar_oferta

# El token que protege la API. En local vive en .env; en Cloud Run vendrá
# de Secret Manager. Si está vacío, NADIE pasa (fail-closed, más seguro).
load_dotenv()
APP_TOKEN = os.environ.get("APP_TOKEN", "")

RUTA_STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # "Calentar" el motor al arrancar: importar herramientas ya crea el cliente
    # OpenAI y deja el CV cacheado en la 1ª petición. Aquí avisamos del estado.
    if not APP_TOKEN:
        print("⚠️  APP_TOKEN vacío: la API rechazará TODO (fail-closed).")
    print("✅ Agente listo. Esperando peticiones.")
    yield
    # (nada que cerrar: sin conexiones persistentes)


app = FastAPI(lifespan=lifespan, title="Agente de búsqueda de empleo")


class Peticion(BaseModel):
    oferta: str


@app.get("/salud")
def salud():
    """Sonda sin token: ¿está vivo el servicio?"""
    return {"estado": "ok", "protegido": bool(APP_TOKEN)}


@app.post("/preguntar")
def preguntar(peticion: Peticion, x_token: str = Header(default="")):
    """Corre el agente sobre una oferta. Exige el token correcto.

    El token es el portero: sin él (o con uno equivocado) → 401, y el agente
    NI se ejecuta (así no gastamos tu API key con desconocidos).
    """
    if x_token != APP_TOKEN or not APP_TOKEN:
        raise HTTPException(status_code=401, detail="Token inválido o ausente.")
    if not peticion.oferta.strip():
        raise HTTPException(status_code=400, detail="La oferta está vacía.")
    return procesar_oferta(peticion.oferta)


# El frontend (Fase 6) se sirve desde /. Montamos static SOLO si existe, para
# que la API funcione ya ahora (sin frontend todavía) sin romper al arrancar.
# Va al final: las rutas de arriba (/salud, /preguntar) tienen prioridad.
if RUTA_STATIC.is_dir():
    app.mount("/", StaticFiles(directory=RUTA_STATIC, html=True), name="static")
