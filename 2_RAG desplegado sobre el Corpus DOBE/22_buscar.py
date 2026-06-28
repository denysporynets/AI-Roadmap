"""
22_buscar.py — RETRIEVAL: busca momentos en el índice A ya congelado
====================================================================
La fase ligera. NO sabe nada de segmentos, multivector ni ensamblaje: solo
CARGA el índice persistente (21_construir_indice.py) y COMPARA. Esa es toda la
gracia de haber separado indexing de retrieval.

Flujo:
  1. carga indice_a.npy (vectores normalizados) + indice_a.json (qué momento es cada puerta)
  2. embebe la consulta y la normaliza
  3. similitud coseno = producto punto contra todas las puertas
  4. agrupa por momento → cada momento se queda con su MEJOR puerta
  5. penaliza es_meta (META_PESO) y devuelve el top-k

Uso:
  ./.venv/bin/python 22_buscar.py "tu consulta en tu propia voz"
  ./.venv/bin/python 22_buscar.py            # modo interactivo (bucle)
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from openai import OpenAI

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"
EMB = BASE / "embeddings"
MODELO = "text-embedding-3-small"
META_PESO = 0.5
TOPK = 5

# Bandas de confianza calibradas en la prueba ciega (28 jun 2026, índice A).
# No filtran: etiquetan. El borde genuino/trampa observado fue estrecho
# (C2 0.404 vs C3 0.394), así que el corte es blando, no un acantilado.
#
# CAVEAT IMPORTANTE (no borrar): estos umbrales son HEURÍSTICOS, inducidos a mano
# a partir de SOLO 8 consultas de una prueba ciega — los cortes se eligieron para
# separar lo que Denys etiquetó como acierto de lo que etiquetó como trampa/fallo.
# Con n=8 la potencia estadística es mínima: el borde 0.40–0.45 lo definen
# literalmente 2 puntos sueltos (C2 0.404 vs C3 0.394). Para un umbral AUDITABLE y
# FIABLE de verdad harían falta muchísimas más pruebas. Sirve para este proyecto
# (educativo: aprender el montaje de un RAG punta a punta), no como valor validado.
# Recalibrar con más consultas reales antes de cualquier uso "en serio".
UMBRAL_CLARO = 0.45     # >=  recuerdo claro
UMBRAL_POSIBLE = 0.40   # 0.40–0.45  vecindario; <0.40  sin recuerdo claro


def banda(sim: float) -> str:
    if sim >= UMBRAL_CLARO:
        return "claro"
    if sim >= UMBRAL_POSIBLE:
        return "posible"
    return "lejano"


def cargar_env() -> None:
    for line in (BASE / ".env").read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")


def main() -> None:
    vecs = np.load(EMB / "indice_a.npy")                       # ya normalizados
    meta = json.loads((EMB / "indice_a.json").read_text())["puertas"]
    corpus = {x["num"]: x for x in json.loads(CORPUS.read_text(encoding="utf-8"))}

    cargar_env()
    client = OpenAI()

    def buscar(consulta: str) -> None:
        e = client.embeddings.create(model=MODELO, input=[consulta]).data[0].embedding
        q = np.asarray(e, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sims = vecs @ q                                        # coseno

        mejor: dict[int, tuple[float, int, int]] = {}         # num → (sim, puerta, n_puertas)
        for s, m in zip(sims, meta):
            s = float(s) * (META_PESO if m["es_meta"] else 1.0)
            if m["num"] not in mejor or s > mejor[m["num"]][0]:
                mejor[m["num"]] = (s, m["puerta"], m["n_puertas"])

        top = sorted(mejor.items(), key=lambda t: -t[1][0])[:TOPK]
        ICONO = {"claro": "🟢", "posible": "🟡", "lejano": "⚪"}
        veredicto = banda(top[0][1][0]) if top else "lejano"
        cabecera = {
            "claro": "recuerdo claro",
            "posible": "posible recuerdo (vecindario)",
            "lejano": "sin recuerdo claro — los aciertos son los menos lejanos, no necesariamente relevantes",
        }[veredicto]
        print(f"\n🔎  «{consulta}»  → {ICONO[veredicto]} {cabecera}\n" + "─" * 64)
        for rank, (num, (s, puerta, n_puertas)) in enumerate(top, 1):
            x = corpus[num]
            preg = x["denys_texto"].replace("\n", " ")[:88]
            tag = "META" if x.get("es_meta") else ("MV" if x.get("es_multivector") else "—")
            via = f"vía puerta {puerta + 1}/{n_puertas}" if n_puertas > 1 else "puerta única"
            print(f"{rank}. {ICONO[banda(s)]} #{num:<4} sim {s:.3f}  [{tag}] {x['pages']}  ({via})")
            print(f"     Denys: {preg}…")
        print()

    args = " ".join(sys.argv[1:]).strip()
    if args:
        buscar(args)
    else:
        print("Modo interactivo. Escribe una consulta (vacío para salir).")
        while True:
            try:
                c = input("\n> ").strip()
            except EOFError:
                break
            if not c:
                break
            buscar(c)


if __name__ == "__main__":
    main()
