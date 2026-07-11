"""
Artefacto 4 · Agente de búsqueda de empleo
La interfaz CLI (Fase 3): un chat de terminal sobre el agente.

Motor vs interfaz: este fichero NO sabe nada de herramientas ni de tool
calls. Solo habla con el humano (lee ofertas, muestra respuestas) y delega
TODO el trabajo a agente(). El mismo motor servirá a la API web de la Fase 4.

Plano conceptual en conceptos/02_cli_del_agente.html.
"""

from agente import agente

BIENVENIDA = """\
╔══════════════════════════════════════════════════════════╗
║   Agente de búsqueda de empleo · Denys Porynets           ║
╠══════════════════════════════════════════════════════════╣
║  Pega una oferta y deja una LÍNEA EN BLANCO para enviarla.║
║  El agente la analiza, la contrasta con tu CV y te        ║
║  redacta un borrador de candidatura.                      ║
║                                                            ║
║  /salir  para terminar  ·  Ctrl-C también                 ║
╚══════════════════════════════════════════════════════════╝"""


def leer_oferta() -> str:
    """Lee texto de varias líneas hasta una línea vacía (o /salir).

    input() lee UNA línea; una oferta ocupa muchas. Acumulamos líneas
    hasta que el usuario deja una en blanco = "ya está, procésalo".
    """
    print("\nPega la oferta (línea en blanco para enviar · /salir para terminar):")
    lineas: list[str] = []
    while True:
        try:
            linea = input()
        except EOFError:                 # Ctrl-D → tratar como salir
            return "/salir"
        if linea.strip() == "/salir":
            return "/salir"
        if linea.strip() == "":          # línea en blanco...
            if lineas:                   #   ...y ya hay contenido → enviar
                break
            continue                     #   ...al principio → ignorar
        lineas.append(linea)
    return "\n".join(lineas)


def main() -> None:
    print(BIENVENIDA)
    while True:                          # bucle EXTERNO · turnos humanos
        try:
            entrada = leer_oferta()
        except KeyboardInterrupt:        # Ctrl-C durante la lectura
            print("\n¡Hasta luego! 👋")
            break

        if entrada.strip() == "/salir":
            print("¡Hasta luego! 👋")
            break

        print("\n🔎 El agente está trabajando…\n")
        try:
            respuesta = agente(          # ← delega TODO al motor (bucle interno)
                f"Analiza esta oferta y prepárame la candidatura:\n{entrada}"
            )
        except KeyboardInterrupt:        # Ctrl-C mientras el agente gira
            print("\n(cancelado) — pega otra oferta o escribe /salir")
            continue
        except Exception as e:           # honestidad: si algo falla, dilo claro
            print(f"⚠️  Algo falló procesando la oferta: {e}")
            continue

        print("\n" + "═" * 60)
        print(respuesta)
        print("═" * 60)


if __name__ == "__main__":
    main()
