"""
eval_jueces.py — LOS JUECES del harness de evaluación (Artefacto 3 · Fase 1)
============================================================================
Dos funciones de "LLM-as-a-judge" que puntúan una respuesta del RAG DOBE:

  · juez_faithfulness(pregunta, contexto, respuesta) → {"score": 1-5, "reason": str}
      ¿La respuesta sale SOLO de los momentos del contexto? ¿No inventa recuerdos?
      (Recibe el contexto: es lo que tiene que verificar.)

  · juez_relevancia(pregunta, respuesta) → {"score": 1-5, "reason": str}
      ¿La respuesta aborda lo que se preguntó? (NO recibe contexto: la relevancia
      se juzga contra la PREGUNTA, no contra los documentos.)

Principios (del resumen 00_resumen_llm_as_judge):
  1. Juez MÁS CAPAZ que el generador. El motor genera con gpt-4o-mini; el juez usa
     gpt-4o → evita el "self-preference bias" (que un modelo se apruebe a sí mismo).
  2. temperature=0 + salida JSON forzada → notas consistentes y parseables.
  3. La RÚBRICA es lo que importa: cada nivel 1-5 descrito con palabras concretas,
     adaptado a memoria EPISÓDICA (no enciclopedia).

Este fichero es CÓDIGO (lógica, no dato): es publicable. Por eso el autotest de
abajo usa ejemplos SINTÉTICOS neutros, nunca contenido real del corpus DOBE.

La clave de OpenAI se busca primero en el entorno y, si no, en un .env (este
directorio o el del Artefacto 2). Mismo patrón que rag_core.py.
"""

import json
import os
from pathlib import Path

from openai import OpenAI

MODELO_JUEZ = "gpt-4o"          # más capaz que el generador (gpt-4o-mini) a propósito
BASE = Path(__file__).parent


def _asegurar_clave() -> None:
    """OPENAI_API_KEY: primero el entorno; si no, un .env (aquí o en el Artefacto 2)."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    candidatos = [
        BASE / ".env",
        BASE.parent / "2_RAG desplegado sobre el Corpus DOBE" / ".env",
    ]
    for env in candidatos:
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return
    raise RuntimeError("Falta OPENAI_API_KEY (ni en el entorno ni en ningún .env).")


# ── RÚBRICAS (adaptadas a memoria episódica) ──────────────────────────────────

RUBRICA_FAITHFULNESS = """Eres un juez imparcial. Evalúas la FIDELIDAD de una respuesta \
respecto a unos MOMENTOS recuperados de una memoria personal (no es una enciclopedia).

Fidelidad = toda afirmación de la respuesta se puede rastrear hasta los momentos dados. \
La respuesta NO debe contener recuerdos, datos o matices que no estén en los momentos \
(eso sería inventar un recuerdo). Admitir que algo no se encuentra en los momentos NO \
penaliza: es lo correcto.

Puntúa de 1 a 5:
1 - Varias afirmaciones no respaldadas por los momentos (inventa recuerdos).
2 - Al menos una afirmación significativa sin respaldo en los momentos.
3 - Mayormente fiel, con detalles menores no respaldados.
4 - Fiel, con extrapolaciones triviales.
5 - Toda afirmación está directamente respaldada por los momentos."""

RUBRICA_RELEVANCIA = """Eres un juez imparcial. Evalúas la RELEVANCIA de una respuesta \
respecto a la PREGUNTA del usuario (no recibes los documentos: solo importa si responde \
a lo que se preguntó).

Relevancia = la respuesta aborda directamente lo que se preguntó. Reconocer límites \
("en estos recuerdos no encuentro...") es válido y relevante si la pregunta no tiene \
respuesta disponible; irse de tema o divagar, no.

Puntúa de 1 a 5:
1 - No aborda la pregunta en absoluto.
2 - La aborda en parte pero se pierde el punto principal.
3 - La aborda pero incluye bastante contenido irrelevante.
4 - La aborda bien, con alguna tangente menor.
5 - Aborda la pregunta de forma directa y completa."""

_FORMATO = '\n\nResponde EXACTAMENTE en JSON: {"score": <entero 1-5>, "reason": "<una frase>"}'


def _juzgar(client: OpenAI, sistema: str, usuario: str) -> dict:
    """Llama al juez con temp 0 + JSON forzado y devuelve {"score": int, "reason": str}."""
    resp = client.chat.completions.create(
        model=MODELO_JUEZ,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": sistema + _FORMATO},
            {"role": "user", "content": usuario},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    return {"score": int(data["score"]), "reason": str(data["reason"]).strip()}


def juez_faithfulness(pregunta: str, contexto: str, respuesta: str, client: OpenAI | None = None) -> dict:
    """¿La respuesta sale solo de los momentos del contexto? Recibe el contexto a verificar."""
    client = client or _cliente()
    usuario = (
        f"PREGUNTA:\n{pregunta}\n\n"
        f"MOMENTOS RECUPERADOS (única fuente válida):\n{contexto}\n\n"
        f"RESPUESTA A EVALUAR:\n{respuesta}"
    )
    return _juzgar(client, RUBRICA_FAITHFULNESS, usuario)


def juez_relevancia(pregunta: str, respuesta: str, client: OpenAI | None = None) -> dict:
    """¿La respuesta aborda lo que se preguntó? NO recibe el contexto a propósito."""
    client = client or _cliente()
    usuario = f"PREGUNTA:\n{pregunta}\n\nRESPUESTA A EVALUAR:\n{respuesta}"
    return _juzgar(client, RUBRICA_RELEVANCIA, usuario)


def _cliente() -> OpenAI:
    _asegurar_clave()
    return OpenAI()


# ── AUTOTEST (Fase 1) · ejemplos SINTÉTICOS neutros, no contenido real del corpus ──
if __name__ == "__main__":
    client = _cliente()

    # Caso BUENO: respuesta fiel al contexto y al grano.
    ctx_bueno = (
        "--- MOMENTO #1 ---\n"
        "DENYS PREGUNTÓ: ¿Cuánto dura la garantía del producto?\n"
        "DEEP RESPONDIÓ: La garantía cubre 2 años desde la compra."
    )
    print("== CASO BUENO (fiel + relevante) ==")
    print("  faithfulness:", juez_faithfulness(
        "¿Cuánto dura la garantía?", ctx_bueno,
        "Según el momento #1, la garantía dura 2 años desde la compra.", client))
    print("  relevancia:  ", juez_relevancia(
        "¿Cuánto dura la garantía?",
        "Según el momento #1, la garantía dura 2 años desde la compra.", client))

    # Caso ALUCINADO: inventa un dato (3 años + extensión) que NO está en el contexto.
    print("\n== CASO ALUCINADO (inventa lo que no está) ==")
    print("  faithfulness:", juez_faithfulness(
        "¿Cuánto dura la garantía?", ctx_bueno,
        "La garantía dura 3 años y puedes extenderla pagando un suplemento.", client))

    # Caso FUERA DE TEMA: responde otra cosa → relevancia baja.
    print("\n== CASO FUERA DE TEMA (no aborda la pregunta) ==")
    print("  relevancia:  ", juez_relevancia(
        "¿Cuánto dura la garantía?",
        "El producto está disponible en tres colores: azul, rojo y verde.", client))

    # Caso ABSTENCIÓN correcta: admite que no encuentra → relevancia alta, no penaliza.
    print("\n== CASO ABSTENCIÓN (admite que no sabe = correcto) ==")
    print("  relevancia:  ", juez_relevancia(
        "¿Cuánto dura la garantía internacional?",
        "En estos recuerdos no encuentro nada sobre la garantía internacional.", client))
