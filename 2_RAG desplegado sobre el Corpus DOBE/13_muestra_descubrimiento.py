"""
13_muestra_descubrimiento.py — MUESTRA DE VALIDACIÓN + DESCUBRIMIENTO (Fase 2)
=============================================================================
Corre la extracción LLM (tema / titulo / semillas) sobre 5 intercambios
VARIADOS, con 'tema' ABIERTO. Objetivo doble:
  1. Validar la CALIDAD del output antes de gastar en los 169.
  2. Ver qué TEMAS emergen -> base para cuajar la taxonomía cerrada.

NO escribe al corpus: solo imprime para revisión y mide tokens reales de salida.
Coste aproximado: ~$0.001.

Uso:  ./.venv/bin/python 13_muestra_descubrimiento.py
"""

import json
import os
import time
from pathlib import Path

from openai import OpenAI, APIError
from pydantic import BaseModel, Field

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"
MODELO = "gpt-4o-mini"
VERSION = "v2"  # versión del prompt (para no pisar resultados anteriores)
PRECIO_IN, PRECIO_OUT = 0.15, 0.60  # $/1M (verificar en openai.com/api/pricing)


# --- cargar la API key del .env sin exponerla ---
def cargar_env() -> None:
    for line in (BASE / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")


# --- esquema de salida estructurada ---
class Enriquecido(BaseModel):
    tema: str = Field(description="categoría temática breve de QUÉ trata el intercambio (2-4 palabras)")
    titulo: str = Field(description="5-8 palabras que resuman el momento de la conversación")
    semillas: list[str] = Field(description="SOLO los temas nuevos y sustanciales que la respuesta abre "
                                            "de pasada, más allá de contestar la pregunta. Número libre; "
                                            "lista VACÍA si la respuesta no abre temas nuevos. No rellenar.")


PROMPT_SISTEMA = (
    "Eres un analista que clasifica intercambios de una conversación de autoconocimiento "
    "(pregunta del usuario + respuesta de una IA). Devuelve tema, titulo y semillas.\n\n"
    "Para las SEMILLAS, sigue este razonamiento:\n"
    "1. Identifica primero cuál es la RESPUESTA DIRECTA a la pregunta.\n"
    "2. Una semilla es ÚNICAMENTE un tema NUEVO y SUSTANCIAL que la respuesta introduce de pasada, "
    "más allá de esa respuesta directa, y que abriría una conversación DISTINTA si el usuario tirara de él.\n\n"
    "Reglas estrictas:\n"
    "- NO son palabras clave, sinónimos ni reformulaciones de la pregunta o del tema principal.\n"
    "- NO inventes ni rellenes hasta un número fijo: extrae solo las que REALMENTE aparezcan.\n"
    "- Si la respuesta se limita a contestar (un resumen, una respuesta corta o muy centrada) sin "
    "abrir temas nuevos, devuelve lista VACÍA [].\n"
    "- Cada semilla debe poder señalarse a una frase concreta del texto.\n\n"
    "Responde solo sobre lo que aparece en el texto, sin inventar. En español."
)


def elegir_muestra(d: list, n: int = 5) -> list:
    """Intercambios conversacionales (con pregunta real, sin tabla), repartidos uniformemente."""
    convers = [x for x in d if x["denys_texto"].strip() and not x.get("es_tabla")]
    paso = max(1, len(convers) // n)
    return [convers[i * paso] for i in range(n)]


def main() -> None:
    cargar_env()
    client = OpenAI()
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    muestra = elegir_muestra(d, 5)

    tok_in = tok_out = 0
    filas = []
    print(f"\n=== MUESTRA DE DESCUBRIMIENTO · {MODELO} · {len(muestra)} intercambios ===\n")

    def parse_con_reintentos(contenido: str, intentos: int = 4):
        for i in range(intentos):
            try:
                return client.responses.parse(
                    model=MODELO,
                    temperature=0,  # reproducible (RAG/extracción: minimizar variabilidad)
                    input=[
                        {"role": "system", "content": PROMPT_SISTEMA},
                        {"role": "user", "content": contenido},
                    ],
                    text_format=Enriquecido,
                )
            except APIError as e:
                if i == intentos - 1:
                    raise
                espera = 2 ** i
                print(f"   ⚠️ {type(e).__name__} (reintento {i + 1}/{intentos - 1} en {espera}s)…")
                time.sleep(espera)

    for x in muestra:
        contenido = f"PREGUNTA:\n{x['denys_texto']}\n\nRESPUESTA:\n{x['ia_texto']}"
        resp = parse_con_reintentos(contenido)
        r = resp.output_parsed
        tok_in += resp.usage.input_tokens
        tok_out += resp.usage.output_tokens

        filas.append({
            "num": x["num"], "pages": x["pages"],
            "n_tok_respuesta": x["n_tok_respuesta"],
            "pregunta": x["denys_texto"],
            "respuesta": x["ia_texto"],
            "tema": r.tema, "titulo": r.titulo,
            "semillas": r.semillas, "n_semillas": len(r.semillas),
        })

        print(f"── #{x['num']}  ({x['pages']}, {x['n_tok_respuesta']} tok respuesta) ──")
        print(f"   pregunta : {x['denys_texto'][:90]}...")
        print(f"   ▸ tema    : {r.tema}")
        print(f"   ▸ titulo  : {r.titulo}")
        print(f"   ▸ semillas: {r.semillas}  (n={len(r.semillas)})")
        print()

    coste = tok_in / 1e6 * PRECIO_IN + tok_out / 1e6 * PRECIO_OUT

    salida = BASE / "FASE2" / f"resultados_muestra_{VERSION}.json"
    salida.write_text(json.dumps({
        "version_prompt": VERSION,
        "modelo": MODELO,
        "prompt_sistema": PROMPT_SISTEMA,
        "coste_usd": round(coste, 5),
        "tok_in": tok_in, "tok_out": tok_out,
        "resultados": filas,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 Resultados volcados a FASE2/{salida.name}")

    print("─" * 50)
    print(f"Tokens reales: entrada {tok_in:,} · salida {tok_out:,}")
    print(f"Media salida/intercambio: {tok_out / len(muestra):.0f} tok "
          f"(el supuesto del medidor era 120)")
    print(f"Coste de esta muestra: ${coste:.5f}")
    print(f"Proyección a 169 (regla de tres): ${coste / len(muestra) * len(d):.4f}")


if __name__ == "__main__":
    main()
