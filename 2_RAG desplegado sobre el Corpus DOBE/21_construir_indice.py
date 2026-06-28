"""
21_construir_indice.py — INDEXING: congela el índice A en disco (una sola vez)
==============================================================================
Hasta ahora el índice A (qué vector es puerta de qué momento) se reensamblaba en
memoria en cada ejecución. Este script lo COSE UNA VEZ y lo guarda, separando la
fase pesada (indexing) de la ligera (retrieval, ver 22_buscar.py).

Regla de ensamblaje (opción A, validada en 20_indice_punto_a.py):
  · es_multivector → sus N vectores de segmento (varias puertas, mismo momento)
  · resto          → su único vector G1 (una puerta)
Los vectores se guardan YA NORMALIZADOS → buscar = un simple producto punto.

Salidas (en embeddings/):
  · indice_a.npy   (P × 1536 float32, vectores normalizados, P = nº de puertas)
  · indice_a.json  (metadatos por puerta: a qué momento apunta, tipo, es_meta…)

Idempotente: re-ejecutar deja el mismo índice. Se rehace solo si cambia el corpus.

Uso:  ./.venv/bin/python 21_construir_indice.py
"""

import json
from datetime import date
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"
EMB = BASE / "embeddings"
OUT_VEC = EMB / "indice_a.npy"
OUT_META = EMB / "indice_a.json"


def norm(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def main() -> None:
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    es_meta = {x["num"]: bool(x.get("es_meta")) for x in d}
    es_mv = {x["num"]: bool(x.get("es_multivector")) for x in d}

    g1 = norm(np.load(EMB / "vectores_g1.npy").astype(np.float32))
    mg1 = json.loads((EMB / "meta_g1.json").read_text())
    nums_g1 = [m["num"] for m in mg1]

    seg = norm(np.load(EMB / "vectores_seg.npy").astype(np.float32))
    owner_seg = np.array(json.loads((EMB / "meta_seg.json").read_text()))

    vecs, meta = [], []
    for vec, num in zip(g1, nums_g1):
        if es_mv.get(num):
            idxs = np.where(owner_seg == num)[0]
            for p, j in enumerate(idxs):                 # una puerta por segmento
                vecs.append(seg[j])
                meta.append({"num": num, "tipo": "seg", "puerta": p,
                             "n_puertas": len(idxs), "es_meta": es_meta.get(num, False)})
        else:
            vecs.append(vec)                             # puerta única G1
            meta.append({"num": num, "tipo": "g1", "puerta": 0,
                         "n_puertas": 1, "es_meta": es_meta.get(num, False)})

    arr = np.asarray(vecs, dtype=np.float32)
    np.save(OUT_VEC, arr)

    n_mv = sum(1 for x in d if es_mv.get(x["num"]))
    manifest = {
        "_manifest": {
            "creado": str(date.today()),
            "opcion": "A · segmento = puerta",
            "modelo_embedding": "text-embedding-3-small",
            "normalizado": True,
            "n_momentos": len(d),
            "n_puertas": len(meta),
            "n_multivector": n_mv,
            "n_meta": sum(es_meta.values()),
            "dim": int(arr.shape[1]),
        },
        "puertas": meta,
    }
    OUT_META.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Índice A congelado en disco:")
    print(f"   {OUT_VEC.name:18} {arr.shape}  ({OUT_VEC.stat().st_size/1024:.0f} KB)")
    print(f"   {OUT_META.name:18} {len(meta)} puertas → {len(d)} momentos")
    print(f"   multivector: {n_mv} momentos abren {len(meta) - (len(d) - n_mv)} puertas de segmento")
    print(f"   mono-vector: {len(d) - n_mv} momentos · 1 puerta cada uno")


if __name__ == "__main__":
    main()
