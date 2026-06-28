"""
Paso 4 — Salida estructurada con Pydantic (texto -> JSON validado).

A diferencia del Paso 3 (texto libre, distinto cada vez), aqui OBLIGAMOS a
Claude a devolver siempre la misma forma: nuestro "molde" Oferta.
El SDK valida la respuesta contra el molde antes de devolvernosla.
"""

from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import anthropic

load_dotenv()
client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# 1) EL MOLDE. Esto define EXACTAMENTE que campos queremos y de que tipo.
#    Las "description" no son adorno: le dicen al modelo que poner en cada campo
#    (es la leccion "label vs description" que viste en el curso de embeddings).
#    Optional[...] = None significa "puede faltar" (p.ej. la empresa a veces no aparece).
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
# 2) La oferta de entrada (de momento fija; en el Paso 5 vendra del CLI).
# ---------------------------------------------------------------------------
OFERTA = """
Buscamos Data Scientist senior para nuestro equipo en Madrid (modelo hibrido,
3 dias oficina). Imprescindible Python, SQL y experiencia poniendo modelos de
Machine Learning en produccion. Se valora GCP y conocimientos de MLOps.
Ofrecemos salario de 45.000 a 55.000 EUR brutos/ano y contrato indefinido.
"""

# ---------------------------------------------------------------------------
# 3) LA LLAMADA con salida estructurada. La unica diferencia con el Paso 3 es
#    el parametro output_format=Oferta. Eso obliga al modelo a rellenar el molde.
# ---------------------------------------------------------------------------
respuesta = client.messages.parse(
    model="claude-opus-4-8",
    max_tokens=500,
    messages=[
        {
            "role": "user",
            "content": f"Extrae los datos de esta oferta de empleo:\n\n{OFERTA}",
        }
    ],
    output_format=Oferta,
)

# 4) parsed_output ya es un objeto Oferta VALIDADO (no texto suelto).
oferta: Oferta = respuesta.parsed_output

print("=== OBJETO PYTHON (ya usable por codigo) ===")
print(oferta)

print("\n=== JSON limpio ===")
print(oferta.model_dump_json(indent=2))

# 5) La PRUEBA de que ahora SI podemos programar sobre los datos:
print("\n=== AHORA SI PODEMOS RAZONAR SOBRE LOS DATOS ===")
if oferta.salario_min and oferta.salario_min >= 40000:
    print(f"-> Cumple tu umbral de salario (>= 40k): {oferta.salario_min} EUR")
else:
    print("-> No alcanza tu umbral de salario, o no se indica salario.")

print(f"-> Numero de tecnologias en el stack: {len(oferta.stack)}")
print(f"-> Tecnologias: {', '.join(oferta.stack)}")

print("\n=== USO ===")
print("tokens entrada:", respuesta.usage.input_tokens)
print("tokens salida :", respuesta.usage.output_tokens)
