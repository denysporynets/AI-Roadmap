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

import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import medidor  # para cerrar la cuenta también cuando la petición revienta
from agente import procesar_oferta
from herramientas import MODELO

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


def bitacora(estado: int, t0: float, resultado: dict | None = None,
             ruta: str = "/preguntar") -> None:
    """Escribe UNA línea JSON por petición en stdout (Artefacto 6, Fase 2).

    En local se ve como una línea de texto; en Cloud Run cada línea de stdout
    la recoge Cloud Logging, y si es JSON válido la indexa CAMPO A CAMPO
    (structured logging): 'severity' se vuelve el nivel del log y el resto
    queda consultable como una tabla ("media de coste_usd donde estado=200").
    No escribimos ficheros ni instalamos agentes: stdout ES el canal.

    `ruta` va como parámetro (no cableada dentro): cuando llegue un segundo
    endpoint, cada uno declara la suya y las consultas no se mezclan.

    flush=True: sin él, el print puede quedarse en el búfer si el contenedor
    muere (escala a cero) y la línea se pierde — justo la que querías ver.
    """
    linea = {
        "severity": "INFO" if estado < 400 else ("WARNING" if estado < 500 else "ERROR"),
        "evento": "peticion",
        "ruta": ruta,
        "estado": estado,
        "latencia_ms": round((time.perf_counter() - t0) * 1000),
        "hora_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if resultado is not None:
        # El código HTTP no cuenta toda la verdad: un 200 con completado=False
        # es el guardarraíl de max_turnos (fallo blando). Por eso va aquí.
        # Con .get()/in: la bitácora observa, y un observador que tira la
        # petición que acaba de pagarse por una clave ausente no es neutral.
        for clave in ("turnos", "completado"):
            if clave in resultado:
                linea[clave] = resultado[clave]
        linea.update(resultado.get("uso") or {})   # llamadas_llm, tokens_*, coste_usd
    print(json.dumps(linea, ensure_ascii=False), flush=True)


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
    t0 = time.perf_counter()
    # compare_digest = comparación en TIEMPO CONSTANTE: tarda lo mismo acierte
    # o falle, así la latencia del 401 no chiva por dónde va el token (un !=
    # normal corta en el primer byte distinto y eso se puede medir).
    if not APP_TOKEN or not secrets.compare_digest(x_token.encode(), APP_TOKEN.encode()):
        bitacora(401, t0)
        raise HTTPException(status_code=401, detail="Token inválido o ausente.")
    if not peticion.oferta.strip():
        bitacora(400, t0)
        raise HTTPException(status_code=400, detail="La oferta está vacía.")
    try:
        resultado = procesar_oferta(peticion.oferta)
    except Exception:
        # La petición que revienta es la MÁS importante de registrar: es la
        # que responde a "¿cuántas fallan?". Se anota y se relanza (el 500
        # real lo produce FastAPI; nosotros solo dejamos constancia).
        # Y se anota CON su coste: el ContextVar del medidor sigue vivo en
        # este hilo, así que lo gastado hasta el crash no se pierde. Un
        # medidor que suma $0 en los fallos sufre sesgo de supervivencia.
        bitacora(500, t0, {"uso": medidor.resumen(MODELO)})
        raise
    bitacora(200, t0, resultado)
    return resultado


# El frontend (Fase 6) se sirve desde /. Montamos static SOLO si existe, para
# que la API funcione ya ahora (sin frontend todavía) sin romper al arrancar.
# Va al final: las rutas de arriba (/salud, /preguntar) tienen prioridad.
if RUTA_STATIC.is_dir():
    app.mount("/", StaticFiles(directory=RUTA_STATIC, html=True), name="static")
