"""
16_dispersion.py — DISPERSION INTERNA REAL (geometría intra-respuesta)
======================================================================
Trocea cada respuesta en segmentos sentence-aware de ~250 tokens (el mismo
tamaño de chunk que usará el RAG final), embebe cada segmento con
text-embedding-3-small y mide cuánto se separan los segmentos entre sí.

  dispersion_interna = distancia coseno MEDIA de cada segmento al centroide
                       de su respuesta  (0 = monólogo coherente · alto = salta
                       entre subtemas → candidata a multi-vector)

Respuestas con 1 solo segmento → dispersion_interna = 0.0 (nada que dispersar).

Salidas:
  · escribe dispersion_interna + n_segmentos en corpus_dobe_enriquecido.json
  · embeddings/vectores_seg.npy  (todos los vectores de segmento, reutilizables)
  · embeddings/meta_seg.json     (a qué intercambio pertenece cada segmento)

Idempotente: si vectores_seg.npy ya existe y no pasas --force, NO re-embebe.

Uso:  ./.venv/bin/python 16_dispersion.py [--force]
"""

import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import tiktoken
from openai import OpenAI

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"
OUT = BASE / "embeddings"
OUT.mkdir(exist_ok=True)
VEC_SEG = OUT / "vectores_seg.npy"
META_SEG = OUT / "meta_seg.json"

MODELO = "text-embedding-3-small"
PRECIO = 0.02            # $/1M tok
ENC = tiktoken.get_encoding("cl100k_base")
TOK_OBJETIVO = 250       # tamaño de ventana (sentence-aware)
LOTE = 100


def cargar_env() -> None:
    for line in (BASE / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")


def frases(texto: str) -> list[str]:
    """Separa en frases por puntuación terminal (. ! ? …)."""
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", texto) if s.strip()]


def segmentar(texto: str, objetivo: int = TOK_OBJETIVO) -> list[str]:
    """Empaqueta frases enteras hasta ~objetivo tokens (sin cortar palabras)."""
    segs, buf, n = [], [], 0
    for fr in frases(texto):
        nf = len(ENC.encode(fr))
        if buf and n + nf > objetivo:
            segs.append(" ".join(buf))
            buf, n = [], 0
        buf.append(fr)
        n += nf
    if buf:
        segs.append(" ".join(buf))
    return segs


def dispersion(vecs: np.ndarray) -> float:
    """Distancia coseno media de cada vector al centroide. 1 vector → 0."""
    if len(vecs) < 2:
        return 0.0
    u = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    centro = u.mean(0)
    centro /= np.linalg.norm(centro) + 1e-9
    cos = u @ centro
    return float((1.0 - cos).mean())


def main() -> None:
    force = "--force" in sys.argv
    d = json.loads(CORPUS.read_text(encoding="utf-8"))

    # 1) segmentar todas las respuestas (local, gratis)
    seg_textos, seg_owner, por_intercambio = [], [], []
    for idx, x in enumerate(d):
        segs = segmentar(x["ia_texto"].strip())
        por_intercambio.append((idx, len(seg_textos), len(segs)))
        for s in segs:
            seg_textos.append(s)
            seg_owner.append(x["num"])
    print(f"{len(d)} respuestas → {len(seg_textos)} segmentos (~{TOK_OBJETIVO} tok c/u)")

    # 2) embeber segmentos (idempotente)
    if VEC_SEG.exists() and not force:
        vecs = np.load(VEC_SEG)
        if len(vecs) != len(seg_textos):
            print(f"⚠️  vectores_seg ({len(vecs)}) ≠ segmentos ({len(seg_textos)}). Usa --force.")
            return
        print(f"✅ Reuso {len(vecs)} vectores de segmento (sin gastar API).")
    else:
        cargar_env()
        client = OpenAI()
        print("Embebiendo segmentos…")
        out, tok = [], 0
        for i in range(0, len(seg_textos), LOTE):
            lote = seg_textos[i:i + LOTE]
            resp = client.embeddings.create(model=MODELO, input=lote)
            out.extend(e.embedding for e in resp.data)
            tok += resp.usage.total_tokens
            print(f"  lote {i // LOTE + 1}: {len(lote)} segmentos")
        vecs = np.array(out, dtype=np.float32)
        np.save(VEC_SEG, vecs)
        META_SEG.write_text(json.dumps(seg_owner, ensure_ascii=False), encoding="utf-8")
        print(f"   Tokens: {tok:,}  ·  Coste: ${tok / 1_000_000 * PRECIO:.4f}")

    # 3) dispersion por intercambio + escribir en el corpus
    valores = []
    for idx, ini, nseg in por_intercambio:
        sub = vecs[ini:ini + nseg]
        disp = dispersion(sub)
        d[idx]["dispersion_interna"] = round(disp, 5)
        d[idx]["n_segmentos"] = nseg
        valores.append((d[idx]["num"], nseg, disp))
    CORPUS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    # 4) resumen
    vals = np.array([v for _, _, v in valores])
    print(f"\n✅ dispersion_interna escrita en corpus ({len(vals)} intercambios)")
    print(f"   min {vals.min():.3f} · mediana {np.median(vals):.3f} · "
          f"media {vals.mean():.3f} · max {vals.max():.3f}")
    print("\nTOP 8 más dispersas (candidatas a multi-vector):")
    for num, nseg, v in sorted(valores, key=lambda t: -t[2])[:8]:
        print(f"   #{num:<4} disp {v:.3f}  ({nseg} segmentos)")
    print("\nTOP 5 más coherentes (1 vector basta):")
    for num, nseg, v in sorted(valores, key=lambda t: t[2])[:5]:
        print(f"   #{num:<4} disp {v:.3f}  ({nseg} segmentos)")


if __name__ == "__main__":
    main()
