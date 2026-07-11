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

# Carga OPENAI_API_KEY desde el .env (blindado, no sube a git).
load_dotenv()
cliente = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Modelo barato y de sobra para extraer datos de un texto.
MODELO = "gpt-4o-mini"


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
    instruccion = (
        "Eres un analista de selección. Extrae los datos clave de la oferta "
        "de empleo que te den. Distingue bien entre requisitos IMPRESCINDIBLES "
        "(los que exige de verdad) y DESEABLES (los que valora pero no exige). "
        "IMPORTANTE sobre requisitos compuestos:\n"
        "  - Si junta varias competencias con 'y'/'and' (todas necesarias, p.ej. "
        "'APIs de LLMs y RAG'), sepáralas en elementos independientes.\n"
        "  - Si ofrece ALTERNATIVAS con 'o'/'or' (basta una, p.ej. 'GCP o AWS'), "
        "NO la separes: déjala como UN solo elemento, p.ej. 'Cloud (GCP o AWS)'.\n"
        "No inventes: si un campo no aparece en la oferta, déjalo vacío ([] o null). "
        "Responde SOLO con un objeto JSON con exactamente estas claves:\n"
        "  puesto            (str)  título del puesto\n"
        "  empresa           (str|null) nombre de la empresa si aparece\n"
        "  seniority         (str)  junior / mid / senior / lead / no indicado\n"
        "  imprescindibles   (list[str]) requisitos exigidos\n"
        "  deseables         (list[str]) requisitos valorados pero no exigidos\n"
        "  responsabilidades (list[str]) qué haría la persona en el puesto\n"
        "  idiomas           (list[str]) idiomas pedidos y nivel si consta\n"
        "  modalidad         (str)  remoto / híbrido / presencial / no indicado"
    )

    respuesta = cliente.chat.completions.create(
        model=MODELO,
        temperature=0,                              # determinista: extraer, no inventar
        response_format={"type": "json_object"},    # obliga a devolver JSON válido
        messages=[
            {"role": "system", "content": instruccion},
            {"role": "user", "content": texto},
        ],
    )
    return json.loads(respuesta.choices[0].message.content)


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

    instruccion = (
        "Eres un asesor de carrera honesto. Compara los requisitos de una oferta "
        "contra el CV que te doy. Básate SOLO en lo que pone el CV: no supongas "
        "experiencia que no aparezca. Un requisito imprescindible que falta es un "
        "BLOQUEANTE y hay que marcarlo como tal. Sé realista, ni optimista ni "
        "derrotista.\n"
        "IDIOMAS — usa el Marco Común Europeo (CEFR), cuyos niveles están ORDENADOS: "
        "A1 < A2 < B1 < B2 < C1 < C2. Un nivel IGUAL O SUPERIOR cumple el requisito "
        "(p.ej. un CV con inglés C1 CUMPLE una oferta que pide inglés B2; NO lo marques "
        "como faltante). Trata 'nativo' o 'bilingüe' como C2.\n"
        "Responde SOLO con un objeto JSON con estas claves:\n"
        "  encaje_global              (str)  alto / medio / bajo\n"
        "  imprescindibles_cumplidos  (list[str]) exigidos que SÍ cumple\n"
        "  imprescindibles_que_faltan (list[str]) exigidos que NO cumple (bloqueantes)\n"
        "  deseables_cumplidos        (list[str]) valorados que ya tiene\n"
        "  puntos_fuertes             (list[str]) dónde destaca para este puesto\n"
        "  veredicto                  (str)  1-2 frases de conclusión"
    )

    contenido_usuario = (
        f"REQUISITOS DE LA OFERTA (JSON):\n{json.dumps(requisitos, ensure_ascii=False)}\n\n"
        f"CV DE LA PERSONA (texto):\n{cv}"
    )

    respuesta = cliente.chat.completions.create(
        model=MODELO,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": instruccion},
            {"role": "user", "content": contenido_usuario},
        ],
    )
    return json.loads(respuesta.choices[0].message.content)


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

    instruccion = (
        "Eres Denys Porynets escribiendo, en primera persona, un mensaje breve "
        "de candidatura (cover letter corta) para una oferta concreta. Tono "
        "cercano y profesional, en el idioma de la oferta. Objetivo: que quien "
        "lo lea quiera conocerte, no que recite tu CV.\n\n"
        "REGLAS DE ESTILO (obligatorias):\n"
        "  - NARRATIVA CUALITATIVA. Cuenta QUÉ resolviste y por qué importó, "
        "no listas de tecnologías ni cifras. Ejemplo: en vez de 'reduje el "
        "tiempo un 87%', di 'automaticé un reporte que antes comía horas cada "
        "semana'.\n"
        "  - NO satures de métricas ni de acrónimos. El ÚNICO número que puedes "
        "usar es el GPA del máster (8.57). Ningún porcentaje, ningún R², nada más.\n"
        "  - Apóyate en los 'puntos_fuertes' del encaje: son los que de verdad "
        "conectan con esta oferta. No prometas experiencia que el CV no sostiene.\n"
        "  - Breve: 130-180 palabras de cuerpo. Sin relleno de plantilla "
        "('Me dirijo a ustedes para...'). Empieza fuerte y personal.\n\n"
        "Responde SOLO con un objeto JSON con estas claves:\n"
        "  asunto  (str)  línea de asunto para el email\n"
        "  cuerpo  (str)  el mensaje completo, listo para revisar y enviar\n"
        "  notas   (list[str]) 2-3 apuntes para Denys: qué personalizaste y "
        "qué debería revisar antes de mandarlo"
    )

    contenido_usuario = (
        f"OFERTA (JSON):\n{json.dumps(oferta, ensure_ascii=False)}\n\n"
        f"ENCAJE CON EL CV (JSON):\n{json.dumps(encaje, ensure_ascii=False)}\n\n"
        f"CV COMPLETO (para sacar ejemplos concretos, NO para copiar cifras):\n{cv}"
    )

    respuesta = cliente.chat.completions.create(
        model=MODELO,
        temperature=0.7,                             # escribir, no extraer: dale voz
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": instruccion},
            {"role": "user", "content": contenido_usuario},
        ],
    )
    return json.loads(respuesta.choices[0].message.content)


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
