"""
api.py — INTERFAZ DE RED del RAG sobre el Corpus DOBE (Fase 2)
=============================================================
Misma filosofía que la Fase 1: el MOTOR (rag_core.MotorRAG) hace el trabajo y
devuelve un dict; esta INTERFAZ solo lo EXPONE por HTTP y lo serializa a JSON.
Aquí no vive ninguna lógica de RAG: si algo del retrieval/síntesis hay que
cambiar, se cambia en rag_core.py y esta API lo hereda gratis.

Nombre SIN prefijo numérico a propósito: uvicorn necesita un módulo importable
`api:app` (no se puede `import 23_responder`).

Endpoints:
  · GET  /salud      → health check SIN token (Cloud Run lo sondea para saber si
                       el contenedor está vivo; no puede traer secretos).
  · POST /preguntar  → recibe {"consulta": "..."}, protegido por cabecera X-Token,
                       devuelve EL MISMO dict que MotorRAG.preguntar().
  · GET  /           → servirá el frontend (Fase 3). Hoy, mientras no exista
                       static/, devuelve una pista de "vivo, usa /preguntar".

Secretos (mismo patrón que rag_core con OPENAI_API_KEY):
  APP_TOKEN se busca PRIMERO en el entorno (Cloud Run / Secret Manager) y SOLO
  si no está, se cae al .env local. Así el mismo código corre en tu Mac y en la
  nube sin tocar nada.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag_core import MotorRAG

BASE = Path(__file__).parent
STATIC = BASE / "static"          # frontend de la Fase 3 (puede no existir aún)


def _cargar_token() -> str:
    """APP_TOKEN: primero el entorno (Cloud Run), luego .env local."""
    tok = os.environ.get("APP_TOKEN")
    if tok:
        return tok
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("APP_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("Falta APP_TOKEN (ni en el entorno ni en .env).")


# ── Ciclo de vida: cargar el motor UNA vez al arrancar ────────────────────────
# El lifespan corre al levantar el servidor (antes de atender a nadie) y al
# apagarlo. Cargamos MotorRAG aquí —índice + corpus + cliente OpenAI— para NO
# pagar ese coste en cada petición. Queda guardado en app.state.
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.motor = MotorRAG()
    app.state.token = _cargar_token()
    yield
    # (nada que cerrar; aquí iría la limpieza si la hubiera)


app = FastAPI(title="RAG DOBE", version="0.2.0", lifespan=lifespan)


# ── Contrato de entrada (Pydantic valida el JSON por nosotros) ────────────────
class Pregunta(BaseModel):
    consulta: str = Field(min_length=1, max_length=2000)


# ── Guardián del token: una "dependencia" que FastAPI ejecuta antes del endpoint ─
# Si el X-Token no coincide con APP_TOKEN, corta con 401 y el endpoint ni se ejecuta.
def exigir_token(x_token: str | None = Header(default=None)) -> None:
    if x_token != app.state.token:
        raise HTTPException(status_code=401, detail="Token inválido o ausente.")


@app.get("/salud")
def salud() -> dict:
    """Health check sin token. Confirma que el contenedor está vivo."""
    return {"estado": "ok"}


@app.post("/preguntar")
def preguntar(p: Pregunta, _=Depends(exigir_token)) -> dict:
    """RAG punta a punta. Devuelve EL MISMO dict que el motor (motor vs interfaz)."""
    return app.state.motor.preguntar(p.consulta)


# ── Frontend ──────────────────────────────────────────────────────────────────
# Si static/ existe (Fase 3), FastAPI sirve ahí el index.html en la raíz. Mientras
# no exista, una pista para que la API no parezca "rota" al abrirla en el navegador.
if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
else:
    @app.get("/", response_class=HTMLResponse)
    def raiz() -> str:
        return (
            "<h1>RAG DOBE · API viva</h1>"
            "<p>El frontend llega en la Fase 3. De momento: "
            "<code>POST /preguntar</code> con cabecera <code>X-Token</code>, "
            "o mira <code>/salud</code>.</p>"
        )
