# Analizador de ofertas de empleo (LLM → JSON estructurado)

> **Artefacto 1** del roadmap *Data Science → AI Engineering*.
> Un mini-servicio CLI que recibe el texto de una oferta de empleo y devuelve sus
> datos en JSON estructurado, llamando al LLM **por SDK directo** (sin frameworks).

## Qué hace

Convierte texto desordenado en datos manejables por código:

```bash
python analizar_oferta.py "Buscamos Data Engineer remoto, Python y Spark, 50k..."
```
```json
{
  "puesto": "Data Engineer",
  "empresa": null,
  "ubicacion": null,
  "modalidad": "remoto",
  "seniority": null,
  "stack": ["Python", "Spark"],
  "salario_min": 50000,
  "salario_max": 50000,
  "contrato": null
}
```

## Por qué

Un LLM por defecto devuelve **texto libre**, distinto en cada llamada, e inservible
para un programa. Este artefacto **fuerza** una salida con forma fija (un molde
[Pydantic](https://docs.pydantic.dev/)) y la **valida** antes de devolverla. Así el
resultado es fiable y se puede usar en código:

```python
if oferta.salario_min >= 40000:   # ahora esto SÍ funciona
    ...
```

## Uso

```bash
# Oferta como argumento
python analizar_oferta.py "texto de la oferta..."

# Oferta desde un fichero
python analizar_oferta.py --archivo oferta.txt

# Guardar el resultado en disco
python analizar_oferta.py --archivo oferta.txt > resultado.json

# Ayuda
python analizar_oferta.py --help
```

## Estructura

| Fichero | Qué es |
|---------|--------|
| `analizar_oferta.py` | **La CLI** (el entregable). Molde `Oferta` + motor + interfaz `argparse`. |
| `01_llamada_cruda.py` | Llamada cruda texto → texto (para ver por qué el texto libre no sirve). |
| `02_salida_estructurada.py` | Molde Pydantic + `messages.parse()` → JSON validado. |
| `03_comparar_openai_claude.py` | La misma extracción con Claude **y** OpenAI (mismo patrón, distinto SDK). |
| `.env.example` | Plantilla de variables de entorno. |

Los ficheros numerados son, además, una bitácora del proceso de construcción.

## Configuración

```bash
pip install anthropic openai pydantic python-dotenv

# Copia la plantilla y rellena tus claves
cp .env.example .env
# edita .env con tus claves reales
```

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
```

> **Seguridad:** las claves viven en `.env`, que está en `.gitignore` y **nunca**
> se sube al repositorio. El código las lee del entorno; jamás están escritas en
> el código fuente.

## Detalle técnico

- **Salida estructurada nativa de cada SDK**: `client.messages.parse(..., output_format=Oferta)`
  en Anthropic; `client.responses.parse(..., text_format=Oferta)` en OpenAI. Ambos
  devuelven un objeto Pydantic ya validado.
- **Modelos por defecto**: `claude-opus-4-8` (Anthropic) y `gpt-4.1` (OpenAI).
- El molde y sus descripciones (`Field(description=...)`) son lo único específico
  del dominio: cambiándolos, el mismo motor extrae facturas, tickets, contratos, etc.
