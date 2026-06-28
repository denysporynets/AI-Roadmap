"""
Paso 3 — Primera llamada CRUDA a Claude (texto -> texto).

Objetivo: ver la llamada al LLM "a pelo", sin frameworks ni schema.
Aqui NO forzamos JSON todavia: el modelo nos devolvera TEXTO LIBRE.
En el Paso 4 veremos por que ese texto libre no nos sirve para un programa,
y como obligar a Claude a devolver datos estructurados.
"""

from dotenv import load_dotenv
import anthropic

# 1) Cargar las claves del fichero .env al entorno del proceso.
load_dotenv()

# 2) Crear el cliente. Por defecto lee ANTHROPIC_API_KEY del entorno,
#    asi que NUNCA escribimos la clave en el codigo.
client = anthropic.Anthropic()

# 3) El texto de entrada: una oferta de empleo real (de momento, fija en el codigo).
#    En el Paso 5 esto vendra de la terminal como argumento del CLI.
OFERTA = """
Buscamos Data Scientist senior para nuestro equipo en Madrid (modelo hibrido,
3 dias oficina). Imprescindible Python, SQL y experiencia poniendo modelos de
Machine Learning en produccion. Se valora GCP y conocimientos de MLOps.
Ofrecemos salario de 45.000 a 55.000 EUR brutos/ano y contrato indefinido.
"""

# 4) LA LLAMADA. Esto es lo unico que de verdad importa hoy.
respuesta = client.messages.create(
    model="claude-opus-4-8",   # nuestro modelo por defecto
    max_tokens=500,            # tope de longitud de la respuesta
    messages=[
        {
            "role": "user",
            "content": f"Extrae los datos clave de esta oferta de empleo:\n\n{OFERTA}",
        }
    ],
)

# 5) La respuesta del modelo viene en una lista de "bloques". El texto esta en el primero.
print("=== RESPUESTA DEL MODELO (texto libre) ===")
print(respuesta.content[0].text)

# 6) Bonus: cuanto ha costado en tokens (entrada + salida).
#    Esto conecta con tu interes en estimar coste antes de gastar.
print("\n=== USO ===")
print("tokens de entrada:", respuesta.usage.input_tokens)
print("tokens de salida :", respuesta.usage.output_tokens)
