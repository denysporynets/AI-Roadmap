"""
Paso 5 — CLI: analizador de ofertas de empleo (texto -> JSON estructurado).

Uso desde la terminal:
    python analizar_oferta.py "Buscamos Data Engineer remoto, Python y Spark, 50k..."
    python analizar_oferta.py --archivo oferta.txt
    python analizar_oferta.py --archivo oferta.txt > resultado.json

La oferta ya NO esta clavada en el codigo: entra desde fuera. Eso es lo que
convierte el script en una herramienta de verdad (Definicion de hecho del artefacto).
"""

import argparse
import sys
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field
import anthropic

load_dotenv()


# ---------------------------------------------------------------------------
# EL MOLDE (igual que en el Paso 4: el "que" que decidimos nosotros).
# ---------------------------------------------------------------------------
class Oferta(BaseModel):
    puesto: str = Field(description="Titulo del puesto, p.ej. 'Data Scientist'")
    empresa: Optional[str] = Field(default=None, description="Nombre de la empresa, o null si no aparece")
    ubicacion: Optional[str] = Field(default=None, description="Ciudad o zona, o null")
    modalidad: Optional[str] = Field(default=None, description="presencial, hibrido o remoto")
    seniority: Optional[str] = Field(default=None, description="junior, mid o senior")
    stack: list[str] = Field(default_factory=list, description="Tecnologias/herramientas mencionadas")
    salario_min: Optional[int] = Field(default=None, description="Salario minimo anual en EUR (solo el numero), o null")
    salario_max: Optional[int] = Field(default=None, description="Salario maximo anual en EUR (solo el numero), o null")
    contrato: Optional[str] = Field(default=None, description="Tipo de contrato, p.ej. indefinido")


# ---------------------------------------------------------------------------
# EL MOTOR (la "fonteneria" separada de la interfaz: funcion reutilizable).
# Recibe texto, devuelve un objeto Oferta validado.
# ---------------------------------------------------------------------------
def analizar(texto: str) -> Oferta:
    client = anthropic.Anthropic()
    respuesta = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=500,
        messages=[
            {"role": "user", "content": f"Extrae los datos de esta oferta de empleo:\n\n{texto}"}
        ],
        output_format=Oferta,
    )
    return respuesta.parsed_output


# ---------------------------------------------------------------------------
# LA INTERFAZ (CLI): lee los argumentos de la terminal y orquesta todo.
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analiza una oferta de empleo y devuelve sus datos en JSON."
    )
    # El usuario pasa la oferta como texto directo...
    parser.add_argument("texto", nargs="?", help="Texto de la oferta entre comillas.")
    # ...o desde un fichero (mas comodo para ofertas largas).
    parser.add_argument("-a", "--archivo", help="Ruta a un fichero de texto con la oferta.")
    args = parser.parse_args()

    # 1) Decidir de donde sacamos el texto de la oferta.
    if args.archivo:
        with open(args.archivo, encoding="utf-8") as f:
            texto = f.read()
    elif args.texto:
        texto = args.texto
    else:
        parser.error("Debes pasar la oferta como texto o con --archivo.")

    if not texto.strip():
        parser.error("La oferta esta vacia.")

    # 2) Llamar al motor, con manejo de errores amable.
    try:
        oferta = analizar(texto)
    except anthropic.APIError as e:
        print(f"Error llamando a la API de Anthropic: {e}", file=sys.stderr)
        sys.exit(1)

    # 3) Imprimir el JSON limpio por la salida estandar (se puede redirigir a un fichero).
    print(oferta.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
