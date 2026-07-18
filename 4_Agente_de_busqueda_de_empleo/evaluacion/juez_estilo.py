"""
juez_estilo.py — EL JUEZ DE ESTILO de la carta (Artefacto 5 · Fase 3 · sub-fase 3c)
===================================================================================
Un "LLM-as-a-judge" que puntúa el ESTILO de una carta de candidatura: lo que las
comprobaciones de Python (los `if` de evaluar_prompts.py) NO saben mirar.

  Los asserts cazan lo OBJETIVO: ¿hay números?, ¿cuántas palabras?, ¿asunto vacío?
  El juez caza lo CUALITATIVO: ¿suena a una persona o a una plantilla robótica?

Nace de un bug real del Artefacto 4: las cartas abrían con "Soy Denys Porynets, un
apasionado ingeniero de IA…" — relleno de plantilla que el prompt PROHÍBE y que
ningún `if` puede detectar. Para eso hace falta otro modelo que LEA la carta.

Patrón heredado del Artefacto 3 (harness de evaluación), sin reinventarlo:
  1. Juez MÁS CAPAZ que el generador. Las cartas las escribe gpt-4o-mini; el juez
     usa gpt-4o → evita el "self-preference bias" (que un modelo se apruebe a sí mismo).
  2. temperature=0 + salida JSON forzada → notas consistentes y parseables.
  3. La RÚBRICA es lo que importa: cada nivel 1-5 descrito con palabras concretas.
  4. Cada nota viaja con su 'reason': una nota sin motivo no es auditable.

Este fichero es CÓDIGO (lógica, no dato): es publicable. Por eso el autotest de
abajo usa cartas SINTÉTICAS neutras, no candidaturas reales.

Se separa a propósito de las comprobaciones baratas: el juez CUESTA (una llamada a
gpt-4o por carta), así que corre a demanda (flag --juez), no en cada medición. Es
justo lo que querrá el CI/CD: asserts en cada push, juez en nightly.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # la raíz, donde vive herramientas.py

from herramientas import cliente  # reutiliza el cliente OpenAI + la carga del .env

MODELO_JUEZ = "gpt-4o"  # más capaz que el generador (gpt-4o-mini): evita self-preference


# ── LA RÚBRICA ────────────────────────────────────────────────────────────────
# Tres criterios, cada uno con sus cinco niveles descritos. El juez es tan bueno
# como esto: "puntúa del 1 al 5" a secas daría notas al azar.

RUBRICA = """Eres un juez imparcial de ESTILO de cartas de presentación (cover \
letters) para candidaturas de empleo. Quien escribe es Denys: perfil de ciencia de \
datos reorientándose a ingeniería de IA, que viene de hostelería y valora una voz \
cercana, honesta y en primera persona, que CUENTA lo que resolvió en vez de recitar \
tecnologías. Evalúas SOLO el estilo y la voz, no los datos técnicos.

Puntúa TRES criterios, cada uno de 1 a 5:

ARRANQUE_SIN_PLANTILLA — ¿cómo abre la carta?
1 - Abre con fórmula de plantilla pura: "Me dirijo a ustedes para...", "Soy Denys \
Porynets, un apasionado ingeniero de IA...", presentarse con el nombre y una etiqueta.
2 - Arranque genérico y previsible, de manual de cartas.
3 - Arranque correcto pero tibio, sin gancho.
4 - Arranque personal que entra bien, evita las fórmulas.
5 - La primera frase engancha: concreta, personal, cero plantilla. Entra por una \
historia o una idea, no por una presentación.

SUENA_A_DENYS — ¿voz humana o texto acartonado?
1 - Robótico: lista de tecnologías y acrónimos, cero narrativa, suena a máquina.
2 - Rígido y corporativo, sin voz propia.
3 - Correcto pero neutro, podría haberlo escrito cualquiera.
4 - Voz personal y cercana, con narrativa cualitativa en su mayor parte.
5 - Claramente una persona en primera persona: cuenta QUÉ resolvió y por qué importó, \
tono cálido y honesto, nada de recitar el CV.

ENGANCHA — ¿da ganas de conocer a quien escribe?
1 - Solo recita méritos; no despierta ningún interés por la persona.
2 - Cumple pero se olvida al momento.
3 - Correcta, ni frío ni calor.
4 - Despierta interés: dan ganas de saber más.
5 - Da claras ganas de conocer a quien escribe y de sentarse a hablar con ella."""

_FORMATO = (
    '\n\nResponde EXACTAMENTE en JSON con esta forma, cada score entero de 1 a 5 y '
    'cada reason en una frase:\n'
    '{"arranque_sin_plantilla": {"score": <1-5>, "reason": "<una frase>"}, '
    '"suena_a_denys": {"score": <1-5>, "reason": "<una frase>"}, '
    '"engancha": {"score": <1-5>, "reason": "<una frase>"}}'
)

CRITERIOS = ("arranque_sin_plantilla", "suena_a_denys", "engancha")


def juzgar_estilo(asunto: str, cuerpo: str, client=None) -> dict:
    """Puntúa el estilo de una carta. Devuelve {criterio: {"score": int, "reason": str}}.

    Args:
        asunto: la línea de asunto de la carta.
        cuerpo: el cuerpo de la carta (lo que de verdad se juzga).
        client: cliente OpenAI opcional (para reutilizarlo en un bucle).

    Returns:
        dict con un {"score", "reason"} por cada criterio de CRITERIOS.
    """
    client = client or cliente
    usuario = f"ASUNTO:\n{asunto}\n\nCUERPO A EVALUAR:\n{cuerpo}"
    resp = client.chat.completions.create(
        model=MODELO_JUEZ,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": RUBRICA + _FORMATO},
            {"role": "user", "content": usuario},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    # Normalizamos a int/str y nos quedamos solo con los tres criterios esperados:
    # si el juez añade ruido, no se cuela; si olvida uno, salta aquí y no en silencio.
    return {
        c: {"score": int(data[c]["score"]), "reason": str(data[c]["reason"]).strip()}
        for c in CRITERIOS
    }


# ── AUTOTEST · cartas SINTÉTICAS neutras, no candidaturas reales ──────────────────
if __name__ == "__main__":
    print(f"juez de estilo · modelo {MODELO_JUEZ}\n")

    # Carta MALA: abre con plantilla ("Soy X, apasionado de...") y recita méritos.
    print("== CARTA DE PLANTILLA (arranque robótico, recita CV) ==")
    mala = (
        "Soy un profesional apasionado por la inteligencia artificial con sólidos "
        "conocimientos en Python, Docker, FastAPI, RAG y despliegue en la nube. "
        "Me dirijo a ustedes para postular al puesto. Poseo amplia experiencia en "
        "el desarrollo de soluciones basadas en modelos de lenguaje y en la "
        "construcción de pipelines de datos escalables. Estoy seguro de que mi "
        "perfil encaja perfectamente con los requisitos de la posición ofertada."
    )
    for k, v in juzgar_estilo("Candidatura", mala).items():
        print(f"  {k:24} {v['score']}/5 — {v['reason']}")

    # Carta BUENA: arranque personal, narrativa cualitativa, voz propia.
    print("\n== CARTA CON VOZ (arranque personal, cuenta una historia) ==")
    buena = (
        "Durante años atendí mesas mientras estudiaba, y ahí aprendí algo que hoy "
        "uso cada día: traducir un problema complicado a algo que cualquiera "
        "entienda. Cuando descubrí que podía automatizar un informe que antes "
        "comía tardes enteras, supe que quería dedicarme a esto. Desde entonces he "
        "llevado un asistente de datos de la idea a funcionar de verdad, "
        "aprendiendo a base de romperlo y arreglarlo. Me haría mucha ilusión "
        "contaros cómo pienso y en qué podría ayudaros."
    )
    for k, v in juzgar_estilo("Hola, os cuento", buena).items():
        print(f"  {k:24} {v['score']}/5 — {v['reason']}")
