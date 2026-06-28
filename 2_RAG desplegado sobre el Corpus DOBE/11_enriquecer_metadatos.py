"""
11_enriquecer_metadatos.py — ENRIQUECIMIENTO DEL CORPUS (por fases)
==================================================================
Añade metadatos a cada intercambio SIN tocar el archivo original.
Lee  corpus_dobe_final.json  ->  escribe  corpus_dobe_enriquecido.json

FASE 1 (este paso) — campos 🟢 GRATIS (local, cero API):
    · n_tok_pregunta   : tokens de denys_texto (tiktoken)
    · n_tok_respuesta  : tokens de ia_texto

FASES SIGUIENTES (aún no, requieren LLM / embeddings):
    · 🔵 tema, titulo, semillas, n_semillas        (LLM generador)
    · 🟡 dispersion_interna, relacionado_con       (tras embeber)
    · 🟡 genealogia (capa 2: semilla -> intercambio posterior)

Uso:  ./.venv/bin/python 11_enriquecer_metadatos.py
"""

import json
from pathlib import Path

import tiktoken

BASE = Path(__file__).parent
ENTRADA = BASE / "corpus_dobe_final.json"
SALIDA = BASE / "corpus_dobe_enriquecido.json"

ENC = tiktoken.get_encoding("cl100k_base")


def n_tok(texto: str) -> int:
    return len(ENC.encode(texto or ""))


def main() -> None:
    d = json.loads(ENTRADA.read_text(encoding="utf-8"))

    for x in d:
        # --- FASE 1: campos gratis ---
        x["n_tok_pregunta"] = n_tok(x["denys_texto"])
        x["n_tok_respuesta"] = n_tok(x["ia_texto"])
        # --- huecos reservados para fases siguientes (None = aún sin calcular) ---
        x.setdefault("tema", None)
        x.setdefault("titulo", None)
        x.setdefault("semillas", None)
        x.setdefault("n_semillas", None)
        x.setdefault("dispersion_interna", None)
        x.setdefault("relacionado_con", None)

    SALIDA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- reporte ---
    tot_q = sum(x["n_tok_pregunta"] for x in d)
    tot_r = sum(x["n_tok_respuesta"] for x in d)
    print(f"✅ Escrito {SALIDA.name}  ·  {len(d)} intercambios enriquecidos")
    print(f"   n_tok_pregunta  total: {tot_q:,}")
    print(f"   n_tok_respuesta total: {tot_r:,}")
    print(f"   Campos por intercambio: {list(d[0].keys())}")
    print(f"\nEjemplo (intercambio #{d[0]['num']}):")
    muestra = {k: d[0][k] for k in
               ['num', 'n_tok_pregunta', 'n_tok_respuesta', 'tema', 'semillas']}
    print("   " + json.dumps(muestra, ensure_ascii=False))


if __name__ == "__main__":
    main()
