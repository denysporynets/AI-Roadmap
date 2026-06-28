"""
Paso 6 — La MISMA extraccion con los dos SDKs (Claude y OpenAI).

Objetivo: comprobar con tus propios ojos que el PATRON es identico
(schema Pydantic -> parse -> objeto validado) y que solo cambia la
sintaxis del SDK. "El SDK por debajo; todo lo demas es conveniencia."
"""

from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import anthropic
from openai import OpenAI

load_dotenv()

# El MISMO molde para los dos proveedores.
class Oferta(BaseModel):
    puesto: str = Field(description="Titulo del puesto")
    empresa: Optional[str] = Field(default=None, description="Empresa, o null")
    ubicacion: Optional[str] = Field(default=None, description="Ciudad o zona, o null")
    modalidad: Optional[str] = Field(default=None, description="presencial, hibrido o remoto")
    seniority: Optional[str] = Field(default=None, description="junior, mid o senior")
    stack: list[str] = Field(default_factory=list, description="Tecnologias mencionadas")
    salario_min: Optional[int] = Field(default=None, description="Salario minimo anual EUR (solo numero), o null")
    salario_max: Optional[int] = Field(default=None, description="Salario maximo anual EUR (solo numero), o null")
    contrato: Optional[str] = Field(default=None, description="Tipo de contrato")


OFERTA = """
Buscamos Data Scientist senior para nuestro equipo en Madrid (modelo hibrido,
3 dias oficina). Imprescindible Python, SQL y experiencia poniendo modelos de
Machine Learning en produccion. Se valora GCP y conocimientos de MLOps.
Ofrecemos salario de 45.000 a 55.000 EUR brutos/ano y contrato indefinido.
"""

PETICION = f"Extrae los datos de esta oferta de empleo:\n\n{OFERTA}"


# --- CLAUDE -----------------------------------------------------------------
def con_claude(texto: str) -> Oferta:
    client = anthropic.Anthropic()
    r = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=500,
        messages=[{"role": "user", "content": texto}],
        output_format=Oferta,          # <-- aqui se pasa el molde
    )
    return r.parsed_output             # <-- aqui sale el objeto validado


# --- OPENAI -----------------------------------------------------------------
def con_openai(texto: str) -> Oferta:
    client = OpenAI()
    r = client.responses.parse(
        model="gpt-4.1",
        input=[{"role": "user", "content": texto}],
        text_format=Oferta,            # <-- mismo molde, parametro con otro nombre
    )
    return r.output_parsed             # <-- mismo concepto, atributo con otro nombre


print("=== CLAUDE (claude-opus-4-8) ===")
print(con_claude(PETICION).model_dump_json(indent=2))

print("\n=== OPENAI (gpt-4.1) ===")
try:
    print(con_openai(PETICION).model_dump_json(indent=2))
except Exception as e:
    # P.ej. 429 insufficient_quota si la cuenta de OpenAI no tiene saldo todavia.
    print(f"(OpenAI no disponible: {type(e).__name__} -> {e})")
