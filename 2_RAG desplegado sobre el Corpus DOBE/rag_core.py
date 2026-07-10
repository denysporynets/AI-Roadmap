"""
rag_core.py — MOTOR del RAG sobre el Corpus DOBE (sin interfaz, sin print)
==========================================================================
Esta es la lógica pura del RAG, extraída de 23_responder.py. NO imprime nada:
DEVUELVE datos estructurados. Así una sola lógica sirve a muchas interfaces
(el CLI 23_responder.py hoy; la API FastAPI mañana → Fase 2).

Principio "motor vs interfaz":
  · El MOTOR (esta clase) hace el trabajo y devuelve un dict.
  · La INTERFAZ (CLI / API) solo PRESENTA ese dict (lo imprime o lo serializa a JSON).

Filosofía RAG (idéntica a 23, no romper):
  1. El UMBRAL manda primero. Si el mejor momento cae en ⚪ (<0.40), NO se llama
     al LLM: se devuelve banda="lejano" y respuesta=None. Ni inventa ni gasta API.
  2. "Definición de hecho": el LLM cita #momento + página; el dict trae `fuentes`.
  3. Memoria EPISÓDICA, no enciclopedia: responde desde los momentos vividos.

Stack: índice A (OpenAI embeddings) + gpt-4o-mini, temperature=0.

La clave de OpenAI se busca PRIMERO en el entorno (os.environ → Cloud Run /
Secret Manager) y SOLO si no está, se cae al fichero .env local. Así el mismo
código corre en tu Mac y en la nube sin tocar nada.
"""

import json
import os
from pathlib import Path

import numpy as np
from openai import OpenAI

BASE = Path(__file__).parent
CORPUS = BASE / "corpus_dobe_enriquecido.json"
EMB = BASE / "embeddings"

MODELO_EMB = "text-embedding-3-small"
MODELO_LLM = "gpt-4o-mini"
META_PESO = 0.5
K_RECUPERAR = 6          # candidatos que trae el retrieval
K_CONTEXTO = 4           # cuántos momentos (>=posible) se le pasan al LLM

# Bandas de confianza (heurísticas, calibradas sobre 8 consultas — ver el CAVEAT
# de 22_buscar.py: n=8, recalibrar con más pruebas antes de cualquier uso "en serio").
UMBRAL_CLARO = 0.45      # >=  recuerdo claro
UMBRAL_POSIBLE = 0.43    # 0.43–0.45 vecindario; <0.43 sin recuerdo claro
                         # Subido de 0.40→0.43 el 29 jun (Artefacto 3, Fase 2): el harness
                         # detecto un falso positivo (contenido AUSENTE colandose en 'posible'
                         # a sim 0.421). Re-evaluacion con 0.43: decision 86%→100%, cero
                         # regresiones en los 7 casos del golden set. Caveat: n=7, vigilar.


def banda(sim: float) -> str:
    if sim >= UMBRAL_CLARO:
        return "claro"
    if sim >= UMBRAL_POSIBLE:
        return "posible"
    return "lejano"


def _asegurar_clave() -> None:
    """OPENAI_API_KEY: primero el entorno (Cloud Run), luego .env local."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                return
    raise RuntimeError("Falta OPENAI_API_KEY (ni en el entorno ni en .env).")


SISTEMA = """Eres el guardián de la memoria episódica de Denys: una colección de \
momentos reales de sus conversaciones con "Deep" durante su proceso de autodescubrimiento \
(corpus DOBE). NO eres una enciclopedia ni un asistente de conocimiento general.

Reglas estrictas:
- Responde ÚNICA y EXCLUSIVAMENTE a partir de los MOMENTOS que se te dan abajo. \
No añadas datos externos ni inventes nada que no esté en ellos.
- Cita siempre de qué momento sale cada cosa, con el formato [#num · pág]. \
Si combinas varios, cita todos.
- Si los momentos no contienen lo necesario para responder, DILO claramente \
("En estos recuerdos no encuentro...") en vez de rellenar con suposiciones.
- Habla en segunda persona a Denys (es SU memoria) y en su idioma (español). \
Tono cercano pero fiel a los hechos: refleja lo que de verdad dijo/pensó, no lo adornes.
- Sé conciso: reconstruye el momento o la postura, no escribas un ensayo."""


class MotorRAG:
    """Carga el índice y el corpus UNA vez; resuelve preguntas en `preguntar()`."""

    def __init__(self) -> None:
        self.vecs = np.load(EMB / "indice_a.npy")                       # ya normalizados
        self.meta = json.loads((EMB / "indice_a.json").read_text())["puertas"]
        self.corpus = {x["num"]: x for x in json.loads(CORPUS.read_text(encoding="utf-8"))}
        _asegurar_clave()
        self.client = OpenAI()

    def recuperar(self, consulta: str) -> list[tuple[int, tuple[float, int, int]]]:
        """Embebe la consulta y devuelve top-K momentos: [(num, (sim, puerta, n_puertas))]."""
        e = self.client.embeddings.create(model=MODELO_EMB, input=[consulta]).data[0].embedding
        q = np.asarray(e, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sims = self.vecs @ q                                            # coseno
        mejor: dict[int, tuple[float, int, int]] = {}                   # num → (sim, puerta, n_puertas)
        for s, m in zip(sims, self.meta):
            s = float(s) * (META_PESO if m["es_meta"] else 1.0)
            if m["num"] not in mejor or s > mejor[m["num"]][0]:
                mejor[m["num"]] = (s, m["puerta"], m["n_puertas"])
        return sorted(mejor.items(), key=lambda t: -t[1][0])[:K_RECUPERAR]

    def preguntar(self, consulta: str) -> dict:
        """RAG punta a punta. Devuelve un dict estructurado (NO imprime)."""
        top = self.recuperar(consulta)
        sim_top = top[0][1][0] if top else 0.0
        veredicto = banda(sim_top)
        cercanos = [{"num": n, "sim": round(t[0], 3)} for n, t in top[:3]]

        base = {
            "consulta": consulta,
            "banda": veredicto,
            "sim_top": round(sim_top, 3),
            "respuesta": None,
            "fuentes": [],
            "cercanos": cercanos,
        }

        # 1) El umbral manda: sin recuerdo claro, ni LLM ni invención.
        if veredicto == "lejano":
            return base

        # 2) Hay recuerdo: armar contexto solo con momentos >= posible.
        usados = [(n, t) for n, t in top if banda(t[0]) != "lejano"][:K_CONTEXTO]
        bloques = []
        for num, (s, _puerta, _n) in usados:
            x = self.corpus[num]
            bloques.append(
                f"--- MOMENTO #{num} · {x['pages']} · (relevancia {s:.2f}) ---\n"
                f"DENYS PREGUNTÓ: {x['denys_texto']}\n"
                f"DEEP RESPONDIÓ: {x['ia_texto']}"
            )
        contexto = "\n\n".join(bloques)
        usuario = (
            f"PREGUNTA DE DENYS A SU MEMORIA:\n{consulta}\n\n"
            f"MOMENTOS RECUPERADOS (úsalos como única fuente):\n\n{contexto}"
        )

        resp = self.client.chat.completions.create(
            model=MODELO_LLM,
            temperature=0,
            messages=[
                {"role": "system", "content": SISTEMA},
                {"role": "user", "content": usuario},
            ],
        )
        base["respuesta"] = resp.choices[0].message.content.strip()
        base["fuentes"] = [{"num": n, "pages": self.corpus[n]["pages"]} for n, _ in usados]
        return base
