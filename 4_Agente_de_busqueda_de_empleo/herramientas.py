"""
Artefacto 4 · Agente de búsqueda de empleo
Herramientas del agente (Fase 1).

Contiene las TRES herramientas del agente:
  1. analizar_oferta   — extrae los requisitos de una oferta (temp 0).
  2. match_cv          — juzga el encaje contra el CV real (temp 0).
  3. redactar_borrador — escribe un mensaje de candidatura (temp 0.7).

Cada herramienta es una función Python normal. Se prueban una a una,
por separado, ANTES de conectarlas al agente (que llega en la Fase 2).
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

import prompts  # los prompts viven versionados ahí, no aquí

# Carga OPENAI_API_KEY desde el .env (blindado, no sube a git).
load_dotenv()
cliente = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Modelo barato y de sobra para extraer datos de un texto.
MODELO = "gpt-4o-mini"


# ─────────────────────────────────────────────────────────────
# LOS MOLDES · el contrato de forma de cada salida (Fase 4 · structured outputs)
# ─────────────────────────────────────────────────────────────
# Antes confiábamos en que el modelo "suele" devolver el JSON bien y lo leíamos
# con json.loads a ciegas: si faltaba una clave, el fallo aparecía tres funciones
# más abajo (un .get() que devuelve None sin avisar). Estos moldes Pydantic son el
# CONTRATO de forma. Se los pasamos al modelo con .parse(), que lo CONSTRIÑE a
# devolver exactamente esta estructura (structured outputs: garantía del
# decodificador, no una súplica en el prompt) y encima nos lo devuelve VALIDADO.

class Oferta(BaseModel):
    puesto: str
    empresa: str | None            # null si la oferta no nombra empresa
    seniority: str
    imprescindibles: list[str]
    deseables: list[str]
    responsabilidades: list[str]
    idiomas: list[str]
    modalidad: str


class Encaje(BaseModel):
    encaje_global: str
    imprescindibles_cumplidos: list[str]
    imprescindibles_que_faltan: list[str]
    deseables_cumplidos: list[str]
    puntos_fuertes: list[str]
    veredicto: str


class Borrador(BaseModel):
    # numeros_detectados va PRIMERO a propósito: es el CoT auditable de v3 (el
    # modelo genera las claves en orden → razona las cifras ANTES de escribir el
    # cuerpo). Se valida como parte del molde y se descarta antes de devolver.
    numeros_detectados: list[str]
    asunto: str
    cuerpo: str
    notas: list[str]


def _parsear(molde: type[BaseModel], temperatura: float, mensajes: list[dict]) -> BaseModel:
    """Llama al modelo con structured outputs y devuelve el objeto ya validado.

    .parse() constriñe la salida al esquema de `molde` y la valida contra él. Si
    el modelo REHÚSA (contenido que no puede o no quiere producir), `.parsed` viene
    vacío y el motivo está en `.refusal`: reventamos aquí a propósito (fail-closed),
    en vez de seguir con un None que rompería silenciosamente más adelante.
    """
    completion = cliente.chat.completions.parse(
        model=MODELO,
        temperature=temperatura,
        response_format=molde,
        messages=mensajes,
    )
    mensaje = completion.choices[0].message
    if mensaje.refusal:
        raise RuntimeError(f"El modelo rehusó producir {molde.__name__}: {mensaje.refusal}")
    if mensaje.parsed is None:
        # Cinturón además de tirantes: el SDK ya lanza si la respuesta se truncó o
        # la filtró; esto cierra cualquier otro hueco sin devolver un None mudo.
        raise RuntimeError(f"El modelo no devolvió un {molde.__name__} válido.")
    return mensaje.parsed


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 1 · analizar_oferta
# ─────────────────────────────────────────────────────────────
def analizar_oferta(texto: str) -> dict:
    """Extrae los requisitos estructurados de una oferta de empleo.

    Recibe el texto libre de una oferta (lo que copias de LinkedIn, InfoJobs…)
    y devuelve un diccionario ordenado con lo que importa para valorar el encaje:
    puesto, seniority, imprescindibles vs deseables, idiomas y modalidad.

    Args:
        texto: el texto completo de la oferta, tal cual copiado.

    Returns:
        dict con las claves: puesto, empresa, seniority, imprescindibles,
        deseables, responsabilidades, idiomas, modalidad.
    """
    instruccion = prompts.obtener("analizar_oferta")

    oferta = _parsear(Oferta, 0, [          # temp 0: extraer, no inventar
        {"role": "system", "content": instruccion},
        {"role": "user", "content": texto},
    ])
    return oferta.model_dump()


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 2 · match_cv
# ─────────────────────────────────────────────────────────────

# Ruta del CV (dato personal, vive blindado en datos_personales/).
# Markdown curado: el modelo lo lee tal cual (títulos, viñetas, negritas
# le dan estructura). Es CONOCIMIENTO para razonar, por eso Markdown y no JSON.
RUTA_CV = Path(__file__).parent / "datos_personales" / "cv_denys.md"

# Cache: el CV se lee UNA sola vez del disco, no en cada llamada.
_cv_texto_cache: str | None = None


def _cargar_cv() -> str:
    """Devuelve el CV en Markdown, leyéndolo del disco solo la 1ª vez."""
    global _cv_texto_cache
    if _cv_texto_cache is None:
        _cv_texto_cache = RUTA_CV.read_text(encoding="utf-8")
    return _cv_texto_cache


def match_cv(requisitos: dict) -> dict:
    """Contrasta los requisitos de una oferta contra el CV de Denys.

    Toma la ficha que produce analizar_oferta (imprescindibles / deseables)
    y dice qué cumple, qué le falta (separando bloqueantes de menores) y
    dónde encaja fuerte. El CV completo se mete en el prompt (context
    stuffing): cabe entero, así que aquí NO hace falta RAG.

    Args:
        requisitos: dict de analizar_oferta (usa imprescindibles y deseables).

    Returns:
        dict con: encaje_global, imprescindibles_cumplidos,
        imprescindibles_que_faltan, deseables_cumplidos, puntos_fuertes, veredicto.
    """
    cv = _cargar_cv()

    instruccion = prompts.obtener("match_cv")

    contenido_usuario = (
        f"REQUISITOS DE LA OFERTA (JSON):\n{json.dumps(requisitos, ensure_ascii=False)}\n\n"
        f"CV DE LA PERSONA (texto):\n{cv}"
    )

    encaje = _parsear(Encaje, 0, [
        {"role": "system", "content": instruccion},
        {"role": "user", "content": contenido_usuario},
    ])
    return encaje.model_dump()


# ─────────────────────────────────────────────────────────────
# HERRAMIENTA 3 · redactar_borrador
# ─────────────────────────────────────────────────────────────
def redactar_borrador(oferta: dict, encaje: dict) -> dict:
    """Redacta un borrador de mensaje de candidatura para una oferta.

    A diferencia de las dos anteriores (que EXTRAEN y JUZGAN, temp 0), esta
    ESCRIBE: por eso sube la temperatura, para que salga voz propia y no un
    texto acartonado. Toma la oferta (analizar_oferta) y el encaje (match_cv)
    y teje un mensaje breve y honesto, apoyado en los puntos fuertes reales.

    Lleva HORNEADAS las reglas de estilo de Denys: narrativa cualitativa, sin
    saturar de métricas técnicas. El único número permitido es el GPA (8.57).

    Args:
        oferta: dict de analizar_oferta (puesto, empresa, responsabilidades…).
        encaje: dict de match_cv (puntos_fuertes, imprescindibles_cumplidos…).

    Returns:
        dict con: asunto, cuerpo, notas (qué se personalizó y avisos a revisar).
    """
    cv = _cargar_cv()

    instruccion = prompts.obtener("redactar_borrador")

    contenido_usuario = (
        f"OFERTA (JSON):\n{json.dumps(oferta, ensure_ascii=False)}\n\n"
        f"ENCAJE CON EL CV (JSON):\n{json.dumps(encaje, ensure_ascii=False)}\n\n"
        f"CV COMPLETO (para sacar ejemplos concretos, NO para copiar cifras):\n{cv}"
    )

    # temp 0.7: escribir, no extraer → dale voz. El molde Borrador sigue exigiendo
    # 'numeros_detectados' primero, así que el CoT auditable de v3 no se pierde.
    borrador = _parsear(Borrador, 0.7, [
        {"role": "system", "content": instruccion},
        {"role": "user", "content": contenido_usuario},
    ]).model_dump()
    # 'numeros_detectados' es el CoT auditable de v2/v3: obliga al modelo a escanear
    # las cifras ANTES de escribir. Cumplida su función, lo descartamos aquí para que
    # ese andamiaje interno no pueda colarse en el borrador que ve el usuario.
    borrador.pop("numeros_detectados", None)
    return borrador


# ─────────────────────────────────────────────────────────────
# PRUEBA SUELTA (solo se ejecuta si corres este fichero directamente)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    oferta_ejemplo = """
    Buscamos AI Engineer (Mid) para incorporarse a nuestro equipo de producto en Madrid.

    Qué harás:
    - Diseñar y desplegar aplicaciones basadas en LLMs (RAG, agentes) en producción.
    - Construir y mantener pipelines de datos y endpoints de inferencia.
    - Colaborar con el equipo de producto para llevar prototipos a Cloud Run.

    Imprescindible:
    - 2+ años con Python.
    - Experiencia con APIs de LLMs (OpenAI o similar) y RAG.
    - Docker y despliegue en la nube (GCP o AWS).
    - Inglés fluido.

    Se valorará:
    - LangChain / LangGraph.
    - Experiencia con FastAPI.
    - Conocimientos de MLOps y CI/CD.

    Modalidad híbrida (3 días oficina en Madrid).
    """

    print("── 1) analizar_oferta ─────────────────────────────")
    requisitos = analizar_oferta(oferta_ejemplo)
    print(json.dumps(requisitos, indent=2, ensure_ascii=False))

    print("\n── 2) match_cv (usa el CV real de Denys) ──────────")
    encaje = match_cv(requisitos)
    print(json.dumps(encaje, indent=2, ensure_ascii=False))

    print("\n── 3) redactar_borrador (mensaje de candidatura) ──")
    borrador = redactar_borrador(requisitos, encaje)
    print(json.dumps(borrador, indent=2, ensure_ascii=False))
