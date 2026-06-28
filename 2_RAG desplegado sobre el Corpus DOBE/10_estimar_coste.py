"""
10_estimar_coste.py — MEDICIÓN DE CONSUMO ANTES DE EMBEBER
==========================================================
Cuenta los tokens reales del corpus con tiktoken (LOCAL, cero llamadas a la API)
y estima el coste de embeber con OpenAI text-embedding-3-small según escenario.

Filosofía DS-NEXUS: medir antes de gastar. Este script NO contacta a OpenAI.
Lo que pagas en producción son los tokens de ENTRADA al modelo de embeddings;
aquí los contamos exactamente para no llevarnos sorpresas.

Uso:  ./.venv/bin/python 10_estimar_coste.py
"""

import json
import statistics as st
from pathlib import Path

import tiktoken

# ---------------------------------------------------------------------------
# PARÁMETROS EDITABLES
# ---------------------------------------------------------------------------
CORPUS = Path(__file__).parent / "corpus_dobe_final.json"

# Precio en USD por 1.000.000 de tokens de entrada.
# ⚠️ VERIFICAR en https://openai.com/api/pricing antes de fiarse:
#    text-embedding-3-small ≈ 0.02 $/1M  (valor a fecha de conocimiento)
#    text-embedding-3-large ≈ 0.13 $/1M
PRECIO_POR_1M = 0.02
MODELO = "text-embedding-3-small"

# Encoding de los embeddings v3 (mismo que GPT-4/3.5): cl100k_base
ENC = tiktoken.get_encoding("cl100k_base")

# Límite de contexto del modelo: nada por encima cabe en UN solo vector.
LIMITE_CONTEXTO = 8191


# ---------------------------------------------------------------------------
def n_tok(texto: str) -> int:
    return len(ENC.encode(texto or ""))


def usd(tokens: int) -> str:
    return f"${tokens / 1_000_000 * PRECIO_POR_1M:.4f}"


def resumen(nombre: str, tokens_por_item: list[int]) -> None:
    total = sum(tokens_por_item)
    tokens_por_item_ord = sorted(tokens_por_item)
    p90 = tokens_por_item_ord[int(len(tokens_por_item_ord) * 0.9)]
    print(f"  {nombre:<34} {total:>9,} tok   ->  {usd(total):>9}"
          f"   (mediana {int(st.median(tokens_por_item)):>4} · p90 {p90:>4} · máx {max(tokens_por_item):>5})")


def main() -> None:
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    print(f"\nCorpus: {CORPUS.name}  ·  {len(d)} intercambios")
    print(f"Modelo: {MODELO}  ·  precio {PRECIO_POR_1M} $/1M tok  ·  encoding cl100k_base\n")

    tok_q = [n_tok(x["denys_texto"]) for x in d]      # preguntas (Denys)
    tok_r = [n_tok(x["ia_texto"]) for x in d]         # respuestas (IA)
    tok_qr = [q + r for q, r in zip(tok_q, tok_r)]    # par completo

    print("ESCENARIOS DE EMBEDDING (lo que se vectoriza · 1 vector por intercambio):")
    resumen("solo pregunta  (B-)", tok_q)
    resumen("solo respuesta (B)", tok_r)
    resumen("pregunta+respuesta (G1/C)", tok_qr)

    # --- Chequeo de outliers que NO caben en un solo embedding ---
    print(f"\nCHEQUEO LÍMITE DE CONTEXTO ({LIMITE_CONTEXTO} tok):")
    excede = [(x["num"], qr) for x, qr in zip(d, tok_qr) if qr > LIMITE_CONTEXTO]
    if excede:
        print(f"  ⚠️ {len(excede)} intercambio(s) superan el límite y OBLIGAN a trocear:")
        for num, t in excede:
            print(f"     · intercambio #{num}: {t:,} tok")
    else:
        mayor = max(tok_qr)
        print(f"  ✅ Ninguno supera el límite (el mayor es {mayor:,} tok). "
              f"Trocear será una decisión de CALIDAD, no una obligación técnica.")

    # --- Coste de experimentar ---
    total_g1 = sum(tok_qr)
    print(f"\nCOSTE DE EXPERIMENTAR (escenario G1, par completo):")
    print(f"  1 pasada    : {usd(total_g1)}")
    print(f"  10 pasadas  : {usd(total_g1 * 10)}")
    print(f"\n(Recordatorio: esto es solo el INDEXADO. El coste de query-time —embedding "
          f"de la consulta + LLM generador— se mide aparte cuando montemos el RAG.)\n")


if __name__ == "__main__":
    main()
