"""
19_aplicar_revision.py — PERSISTE las 16 decisiones validadas por Denys
=======================================================================
Tras revisar REVISION_DISPERSION.html, Denys confirmó la clasificación de los
16 intercambios más dispersos. Este script graba esa decisión como METADATO en
corpus_dobe_enriquecido.json. NO genera vectores todavía: solo pone banderas.

  · es_meta        = True  → digest / traspaso de contexto / meta-consulta.
                            Se le bajará peso o se excluirá del retrieval por
                            defecto. (4 intercambios)
  · es_multivector = True  → multi-tema REAL. Cuando montemos el índice tendrá
                            VARIAS puertas de entrada (varios vectores) hacia
                            el MISMO payload-momento. (12 intercambios)

Todo intercambio NO listado queda con ambos flags = False (mono-vector normal).

Idempotente: se puede re-ejecutar; deja siempre el mismo estado.
Reversible:  son solo dos campos booleanos; borrarlos no destruye nada.

Uso:  ./.venv/bin/python 19_aplicar_revision.py
"""

import json
from pathlib import Path

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"

# Decisiones validadas por Denys (28/06) sobre REVISION_DISPERSION.html
META = {45, 168, 124, 7}                                   # 4 → es_meta
MULTIVECTOR = {2, 6, 18, 49, 66, 67, 77, 125, 154, 190, 252, 266}  # 12 → es_multivector


def main() -> None:
    d = json.loads(CORPUS.read_text(encoding="utf-8"))
    nums = {x["num"] for x in d}

    # comprobación de integridad: que todos los nums existan en el corpus
    faltan = (META | MULTIVECTOR) - nums
    if faltan:
        print(f"⚠️  nums no encontrados en el corpus: {sorted(faltan)}")
        return

    n_meta = n_mv = 0
    for x in d:
        es_meta = x["num"] in META
        es_mv = x["num"] in MULTIVECTOR
        x["es_meta"] = es_meta
        x["es_multivector"] = es_mv
        n_meta += es_meta
        n_mv += es_mv

    CORPUS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Flags grabados en {CORPUS.name}")
    print(f"   es_meta        = True → {n_meta:>3} intercambios  {sorted(META)}")
    print(f"   es_multivector = True → {n_mv:>3} intercambios  {sorted(MULTIVECTOR)}")
    print(f"   mono-vector normal     → {len(d) - n_meta - n_mv:>3} intercambios")


if __name__ == "__main__":
    main()
