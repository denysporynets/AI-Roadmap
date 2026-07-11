"""
Artefacto 4 · Agente de búsqueda de empleo
El AGENTE (Fase 2): el bucle piensa → actúa → observa.

En la Fase 1 llamábamos las 3 herramientas a mano, en orden. Aquí se las
damos al modelo y es ÉL quien decide cuál usar, en qué orden y cuándo ha
terminado. El bucle de function calling lo escribimos a mano (no LangGraph)
para verlo girar: ese es el propósito del artefacto.

Plano conceptual completo en conceptos/01_bucle_del_agente.html.
"""

import json

# Reutilizamos el mismo cliente, modelo y las 3 herramientas de la Fase 1.
# No hay stack nuevo: el agente ORQUESTA lo que ya construimos y probamos.
from herramientas import (
    cliente,
    MODELO,
    analizar_oferta,
    match_cv,
    redactar_borrador,
)


# ─────────────────────────────────────────────────────────────
# 1) EL MENÚ · qué herramientas ve el modelo (tool schema)
# ─────────────────────────────────────────────────────────────
# Una ficha por herramienta: nombre + para qué sirve + qué argumentos toma.
# El modelo ELIGE leyendo la 'description', así que esa frase es prompt
# engineering, no adorno. Es la misma firma de las funciones de la Fase 1,
# traducida a un formato que el LLM entiende.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analizar_oferta",
            "description": (
                "Extrae los requisitos estructurados de una oferta de empleo en "
                "texto libre: puesto, seniority, imprescindibles vs deseables, "
                "idiomas y modalidad. Úsala SIEMPRE primero, sobre el texto crudo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "El texto completo de la oferta, tal cual copiado.",
                    }
                },
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "match_cv",
            "description": (
                "Contrasta los requisitos de una oferta contra el CV de Denys y "
                "dice qué cumple, qué le falta y dónde encaja fuerte. Úsala después "
                "de analizar_oferta, pasándole su resultado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requisitos": {
                        "type": "object",
                        "description": "El dict que devolvió analizar_oferta.",
                    }
                },
                "required": ["requisitos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "redactar_borrador",
            "description": (
                "Redacta un borrador de mensaje de candidatura para la oferta, "
                "apoyado en los puntos fuertes del encaje. Úsala en último lugar, "
                "cuando ya tengas la oferta analizada y el encaje calculado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "oferta": {
                        "type": "object",
                        "description": "El dict que devolvió analizar_oferta.",
                    },
                    "encaje": {
                        "type": "object",
                        "description": "El dict que devolvió match_cv.",
                    },
                },
                "required": ["oferta", "encaje"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────
# 2) EL DESPACHADOR · de un nombre a una función de Python
# ─────────────────────────────────────────────────────────────
# El mapa nombre → función real. Cuando el modelo pide "match_cv", esto es
# lo que corre de verdad en tu Mac.
DISPATCH = {
    "analizar_oferta": analizar_oferta,
    "match_cv": match_cv,
    "redactar_borrador": redactar_borrador,
}


def ejecutar_herramienta(tc) -> dict:
    """Ejecuta la herramienta que pidió el modelo y empaqueta el resultado.

    Ojo al detalle que engaña: tc.function.arguments NO es un dict, es un
    STRING con JSON dentro (lo escribió el modelo). Por eso el json.loads.
    El tool_call_id cose esta respuesta con la petición exacta.
    """
    nombre = tc.function.name
    args = json.loads(tc.function.arguments)   # JSON como texto → dict
    funcion = DISPATCH[nombre]
    resultado = funcion(**args)                # ← corre TU código de la Fase 1
    return {
        "role": "tool",
        "tool_call_id": tc.id,
        "content": json.dumps(resultado, ensure_ascii=False),
    }


# ─────────────────────────────────────────────────────────────
# 3) LAS INSTRUCCIONES · quién es el agente y cómo orquesta
# ─────────────────────────────────────────────────────────────
SYSTEM = (
    "Eres el asistente de búsqueda de empleo de Denys Porynets. Cuando te pegue "
    "el texto de una oferta, tu trabajo tiene tres pasos, en este orden:\n"
    "  1. analizar_oferta sobre el texto crudo.\n"
    "  2. match_cv con los requisitos que salgan del paso 1.\n"
    "  3. redactar_borrador con la oferta analizada y el encaje del paso 2.\n"
    "Cada paso toma la salida del anterior. No inventes datos del CV: básate solo "
    "en lo que devuelvan las herramientas. Cuando tengas el borrador, cierra con un "
    "resumen breve para Denys: nivel de encaje, qué imprescindibles le faltan (si "
    "hay), y entrégale el borrador listo para revisar."
)


# ─────────────────────────────────────────────────────────────
# 4) EL BUCLE · piensa → actúa → observa (ReAct, a mano)
# ─────────────────────────────────────────────────────────────
def _correr_bucle(peticion_usuario: str, max_turnos: int = 6, verboso: bool = True) -> dict:
    """Corre el agent loop hasta la respuesta final. Es el MOTOR reutilizable.

    Devuelve un dict (no solo texto) para que cualquier interfaz —CLI o API—
    tenga tanto la respuesta como la traza de pasos. Es el mismo principio que
    `rag_core.py` del Artefacto 2: un núcleo que devuelve datos estructurados.

    Args:
        peticion_usuario: lo que pega el usuario (p.ej. el texto de una oferta).
        max_turnos: guardarraíl. Tope de vueltas para que nunca sea infinito.
        verboso: si True, narra el bucle por pantalla (para VER el loop girar).

    Returns:
        dict con: respuesta (str), pasos (list[str] de herramientas usadas),
        turnos (int), completado (bool: False si agotó max_turnos sin cerrar).
    """
    # La "memoria" del agente no es magia: es esta lista, que va creciendo.
    # La API es stateless, así que en cada vuelta le reenviamos todo.
    mensajes = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": peticion_usuario},
    ]
    pasos: list[str] = []                  # traza: qué herramientas se usaron y en qué orden

    for turno in range(1, max_turnos + 1):
        # PIENSA: el modelo mira toda la conversación y decide.
        resp = cliente.chat.completions.create(
            model=MODELO,
            temperature=0,                 # orquestar es decidir, no crear: determinista
            messages=mensajes,
            tools=TOOLS,                   # ← le pasamos el menú
        )
        msg = resp.choices[0].message
        mensajes.append(msg)               # 1) guarda SIEMPRE lo que dijo el modelo

        # 2) ¿No pide herramientas? Entonces ha terminado: esta es la respuesta.
        if not msg.tool_calls:
            if verboso:
                print(f"\n── turno {turno}: respuesta final ─────────────")
            return {"respuesta": msg.content, "pasos": pasos,
                    "turnos": turno, "completado": True}

        # 3) ACTÚA + OBSERVA: ejecuta cada herramienta pedida y devuelve el resultado.
        if verboso:
            pedidas = ", ".join(tc.function.name for tc in msg.tool_calls)
            print(f"── turno {turno}: el modelo pide → {pedidas}")
        for tc in msg.tool_calls:
            resultado = ejecutar_herramienta(tc)
            pasos.append(tc.function.name)
            if verboso:
                vista = resultado["content"]
                vista = vista[:120] + "…" if len(vista) > 120 else vista
                print(f"     ✓ {tc.function.name} → {vista}")
            mensajes.append(resultado)

    # Guardarraíl: si agota los turnos sin cerrar, cortamos con honestidad.
    return {"respuesta": "⚠️ Se alcanzó el máximo de turnos sin respuesta final.",
            "pasos": pasos, "turnos": max_turnos, "completado": False}


def agente(peticion_usuario: str, max_turnos: int = 6, verboso: bool = True) -> str:
    """Envoltorio fino para el CLI: corre el motor y devuelve solo el texto."""
    return _correr_bucle(peticion_usuario, max_turnos, verboso)["respuesta"]


def procesar_oferta(texto: str, max_turnos: int = 6) -> dict:
    """Envoltorio para la API: recibe el texto crudo de una oferta y orquesta.

    Añade la instrucción de encuadre y llama al motor en silencio (sin prints,
    que en un servidor no sirven). Devuelve el dict entero (respuesta + pasos).
    """
    peticion = f"Analiza esta oferta y prepárame la candidatura:\n{texto}"
    return _correr_bucle(peticion, max_turnos, verboso=False)


# ─────────────────────────────────────────────────────────────
# PRUEBA SUELTA · ver el bucle girar sobre una oferta real
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    oferta_ejemplo = """
    Buscamos AI Engineer (Mid) para incorporarse a nuestro equipo de producto en Madrid.

    Qué harás:
    - Diseñar y desplegar aplicaciones basadas en LLMs (RAG, agentes) en producción.
    - Construir y mantener pipelines de datos y endpoints de inferencia.
    - Colaborar con el equipo de producto para llevar prototipos a Cloud Run.

    Imprescindible:
    - 2+ años con Python.
    - Experiencia con APIs de LLMs (OpenAI o similar) y RAG.
    - Docker y despliegue en la nube (GCP o AWS).
    - Inglés fluido.

    Se valorará:
    - LangChain / LangGraph.
    - Experiencia con FastAPI.
    - Conocimientos de MLOps y CI/CD.

    Modalidad híbrida (3 días oficina en Madrid).
    """

    print("═══ EL AGENTE GIRA ═══════════════════════════════")
    respuesta = agente(f"Analiza esta oferta y prepárame la candidatura:\n{oferta_ejemplo}")
    print("\n═══ RESPUESTA FINAL AL USUARIO ═══════════════════")
    print(respuesta)
