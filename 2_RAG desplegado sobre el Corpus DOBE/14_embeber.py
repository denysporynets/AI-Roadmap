"""
14_embeber.py — EMBEDDINGS G1 (un vector por intercambio = par P+R)
==================================================================
Embebe cada intercambio completo con text-embedding-3-small y guarda los
vectores en embeddings/vectores_g1.npy + metadatos en embeddings/meta_g1.json.

Idempotente: si los vectores ya existen, NO vuelve a llamar a la API (no paga
dos veces). Usar --force para re-embeber.

Uso:  ./.venv/bin/python 14_embeber.py [--force]
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from openai import OpenAI

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"
OUT = BASE / "embeddings"
OUT.mkdir(exist_ok=True)
VEC = OUT / "vectores_g1.npy"
META = OUT / "meta_g1.json"

MODELO = "text-embedding-3-small"
PRECIO = 0.02  # $/1M tok (verificar en openai.com/api/pricing)
LOTE = 100


def cargar_env() -> None:
    for line in (BASE / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")


def main() -> None:
    force = "--force" in sys.argv
    if VEC.exists() and not force:
        arr = np.load(VEC)
        print(f"✅ Ya existen los vectores ({arr.shape}). No re-embebo. (usa --force para rehacer)")
        return

    cargar_env()
    client = OpenAI()
    d = json.loads(CORPUS.read_text(encoding="utf-8"))

    # G1 = intercambio completo (par pregunta + respuesta)
    items = []
    for x in d:
        texto = (x["denys_texto"].strip() + "\n\n" + x["ia_texto"].strip()).strip()
        if texto:
            items.append((x, texto))

    print(f"Embebiendo {len(items)} intercambios (G1 = par P+R) con {MODELO}…")
    vectores, tok = [], 0
    for i in range(0, len(items), LOTE):
        lote = items[i:i + LOTE]
        resp = client.embeddings.create(model=MODELO, input=[t for _, t in lote])
        vectores.extend(e.embedding for e in resp.data)
        tok += resp.usage.total_tokens
        print(f"  lote {i // LOTE + 1}: {len(lote)} vectores")

    arr = np.array(vectores, dtype=np.float32)
    np.save(VEC, arr)

    meta = [{
        "num": x["num"], "pages": x["pages"],
        "n_tok_pregunta": x["n_tok_pregunta"], "n_tok_respuesta": x["n_tok_respuesta"],
        "pregunta": x["denys_texto"][:160], "tema": x.get("tema"),
    } for x, _ in items]
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    coste = tok / 1_000_000 * PRECIO
    print(f"\n✅ Guardados {arr.shape[0]} vectores de dim {arr.shape[1]} → embeddings/{VEC.name}")
    print(f"   Tokens reales: {tok:,}  ·  Coste real: ${coste:.4f}")


if __name__ == "__main__":
    main()
