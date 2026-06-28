"""
12_estimar_coste_llm.py — MEDICIÓN DE COSTE DE LA FASE 2 (enriquecimiento con LLM)
=================================================================================
Estima cuánto costará pedirle a un LLM (gpt-4o-mini) que extraiga
tema / titulo / semillas de cada intercambio. NO llama a la API: cuenta los
tokens de ENTRADA con tiktoken y estima los de SALIDA con un supuesto.

(El output no se puede contar a priori porque aún no existe; lo estimamos con
un supuesto conservador y dejamos el precio como variable editable.)

Uso:  ./.venv/bin/python 12_estimar_coste_llm.py
"""

import json
from pathlib import Path

import tiktoken

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"

# --- Precios USD por 1M tokens (⚠️ VERIFICAR en openai.com/api/pricing) ---
MODELO = "gpt-4o-mini"
PRECIO_IN = 0.15   # $/1M tok de entrada
PRECIO_OUT = 0.60  # $/1M tok de salida

# Supuesto de salida por intercambio (tema~5 + titulo~12 + 3 semillas~20 + JSON ~> )
SUP_TOK_SALIDA = 120

# gpt-4o-mini usa el encoding o200k_base
ENC = tiktoken.get_encoding("o200k_base")

# Borrador del prompt de sistema (cuenta como tokens fijos por llamada)
PROMPT_SISTEMA = """Eres un analista que clasifica intercambios de una conversación de \
autoconocimiento (pregunta del usuario + respuesta de una IA). Para cada intercambio \
devuelve un JSON con: 'tema' (categoría temática breve), 'titulo' (5-8 palabras que \
resuman el momento), y 'semillas' (lista de los temas TANGENCIALES que la respuesta \
introduce además de responder a la pregunta; [] si no hay ninguno). Responde solo \
sobre lo que aparece en el texto, sin inventar."""


def n_tok(texto: str) -> int:
    return len(ENC.encode(texto or ""))


def usd(tok: int, precio: float) -> float:
    return tok / 1_000_000 * precio


def main() -> None:
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    tok_sistema = n_tok(PROMPT_SISTEMA)

    # entrada por intercambio = prompt sistema (se repite en cada llamada) + par P+R
    tok_in_total = 0
    for x in d:
        contenido = f"PREGUNTA:\n{x['denys_texto']}\n\nRESPUESTA:\n{x['ia_texto']}"
        tok_in_total += tok_sistema + n_tok(contenido)

    tok_out_total = SUP_TOK_SALIDA * len(d)

    coste_in = usd(tok_in_total, PRECIO_IN)
    coste_out = usd(tok_out_total, PRECIO_OUT)

    print(f"\nFASE 2 · enriquecimiento con {MODELO} (encoding o200k_base)")
    print(f"Corpus: {len(d)} intercambios  ·  prompt de sistema = {tok_sistema} tok/llamada\n")
    print(f"  ENTRADA  : {tok_in_total:>9,} tok  ->  ${coste_in:.4f}  (precio {PRECIO_IN} $/1M)")
    print(f"  SALIDA   : {tok_out_total:>9,} tok  ->  ${coste_out:.4f}  (supuesto {SUP_TOK_SALIDA} tok/item · {PRECIO_OUT} $/1M)")
    print(f"  {'TOTAL':<9}: {tok_in_total + tok_out_total:>9,} tok  ->  ${coste_in + coste_out:.4f}\n")
    print(f"  Muestra de validación (5 intercambios): ~${(coste_in + coste_out) * 5 / len(d):.4f}\n")


if __name__ == "__main__":
    main()
