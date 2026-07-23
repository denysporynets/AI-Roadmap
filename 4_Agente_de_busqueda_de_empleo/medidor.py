"""
Artefacto 6 · Despliegue en producción real
El MEDIDOR (Fase 1): cuenta lo que cada petición consume de verdad.

Cada respuesta de la API de OpenAI trae un objeto `usage` con los tokens
exactos que costó ESA llamada. Hasta hoy lo tirábamos sin mirarlo. Este
módulo lo recoge y lo suma POR PETICIÓN: el bucle del agente y las
herramientas llaman a registrar(), y al final resumen() cierra la cuenta
con su coste en dólares.

¿Por qué ContextVar y no una variable global normal? Porque en producción
pueden atenderse DOS peticiones a la vez (Cloud Run sirve varias en paralelo
dentro del mismo contenedor). Con un contador global, los tokens de una
petición se sumarían a los de otra: contaminación cruzada. ContextVar se usa
como una global, pero cada petición ve su PROPIO carril — aislamiento
estructural, el mismo principio que los namespaces de Pinecone.
"""

from contextvars import ContextVar

# Precios oficiales por MILLÓN de tokens (platform.openai.com → Pricing).
# Entrada (lo que el modelo LEE) y salida (lo que ESCRIBE) se cobran distinto:
# generar cuesta ~4× más que leer. Si el modelo cambia, se añade su fila aquí.
PRECIOS_USD_POR_MILLON = {
    "gpt-4o-mini": {"entrada": 0.15, "salida": 0.60},
}

# El contador de la petición en curso. default=None = "no hay petición abierta".
_uso: ContextVar[dict | None] = ContextVar("uso_peticion", default=None)


def iniciar() -> None:
    """Abre el contador de la petición actual, a cero."""
    _uso.set({"llamadas_llm": 0, "tokens_entrada": 0, "tokens_salida": 0})


def registrar(usage) -> None:
    """Suma el `usage` de UNA llamada al LLM al contador de la petición.

    Si no hay contador abierto (p.ej. un script suelto que usa las
    herramientas sin pasar por el bucle), no rompe: simplemente no cuenta.
    Y si `usage` llega vacío (respuesta rara del proveedor), tampoco: el
    medidor OBSERVA — jamás debe tumbar la petición que está midiendo.
    """
    datos = _uso.get()
    if datos is None or usage is None:
        return
    datos["llamadas_llm"] += 1
    datos["tokens_entrada"] += usage.prompt_tokens
    datos["tokens_salida"] += usage.completion_tokens


def resumen(modelo: str) -> dict:
    """Cierra la cuenta: tokens totales + coste en dólares según el modelo."""
    datos = _uso.get() or {"llamadas_llm": 0, "tokens_entrada": 0, "tokens_salida": 0}
    precios = PRECIOS_USD_POR_MILLON.get(modelo)
    if precios is None:
        # Modelo sin fila en la tabla: mejor un "no sé" honesto que un número inventado.
        coste = None
    else:
        coste = (datos["tokens_entrada"] / 1_000_000 * precios["entrada"]
                 + datos["tokens_salida"] / 1_000_000 * precios["salida"])
    return {**datos, "coste_usd": None if coste is None else round(coste, 6)}
