"""
23_responder.py — CLI (interfaz de terminal) sobre el motor rag_core.py
=======================================================================
Desde la Fase 1, TODA la lógica RAG vive en `rag_core.py` (el motor). Este
fichero es solo una INTERFAZ fina: pide una pregunta, llama a `motor.preguntar()`
y PRESENTA el dict resultante en la terminal (🟢🟡⚪ + 📎 Fuentes).

Misma filosofía que antes (el umbral manda; sin recuerdo claro no se llama al LLM);
ahora esa decisión la toma el motor y aquí solo se muestra. La API de la Fase 2
reutilizará EXACTAMENTE el mismo motor, solo que serializando el dict a JSON.

Uso:
  ./.venv/bin/python 23_responder.py "tu pregunta a tu memoria"
  ./.venv/bin/python 23_responder.py            # modo interactivo (bucle)
"""

import sys

from rag_core import MotorRAG, UMBRAL_POSIBLE


def mostrar(r: dict) -> None:
    """Presenta en terminal el dict que devuelve el motor."""
    print(f"\n🔎  «{r['consulta']}»\n" + "─" * 68)

    if r["banda"] == "lejano":
        print("⚪  No guardo un recuerdo claro de esto.")
        print(f"    (lo más cercano cae en sim {r['sim_top']:.3f}, por debajo del umbral {UMBRAL_POSIBLE})")
        cercanos = ", ".join(f"#{c['num']}" for c in r["cercanos"])
        print(f"    Lo más próximo, por si quieres mirarlo a mano: {cercanos}\n")
        return

    icono = "🟢" if r["banda"] == "claro" else "🟡"
    n = len(r["fuentes"])
    plural = "momento" if n == 1 else "momentos"
    print(f"{icono}  Respuesta (síntesis sobre {n} {plural}):\n")
    print(r["respuesta"])
    fuentes = " · ".join(f"#{f['num']} ({f['pages']})" for f in r["fuentes"])
    print(f"\n📎  Fuentes: {fuentes}\n")


def main() -> None:
    motor = MotorRAG()
    args = " ".join(sys.argv[1:]).strip()
    if args:
        mostrar(motor.preguntar(args))
    else:
        print("Modo interactivo. Escribe una pregunta a tu memoria (vacío para salir).")
        while True:
            try:
                c = input("\n> ").strip()
            except EOFError:
                break
            if not c:
                break
            mostrar(motor.preguntar(c))


if __name__ == "__main__":
    main()
