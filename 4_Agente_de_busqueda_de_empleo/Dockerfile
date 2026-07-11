# Dockerfile — receta de la imagen del Agente de empleo (Fase 5)
# ==============================================================
# Una "caja" reproducible con Python + librerías + herramientas + motor + API
# + CV + frontend. Se construye en la nube (Cloud Build); aquí solo la receta.

# 1) Base mínima: Python 3.13 "slim" (sin extras de SO que no usamos).
FROM python:3.13-slim

# Buenas prácticas de contenedor:
#   PYTHONDONTWRITEBYTECODE → no genera .pyc (imagen más limpia)
#   PYTHONUNBUFFERED        → logs en vivo (se ven en Cloud Run sin retraso)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 2) Dependencias PRIMERO (capa cacheable): si solo cambias código, no reinstala.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Solo lo MÍNIMO para servir, nombrado explícitamente (lista blanca).
#    Copiando solo esto, el .env NUNCA puede colarse en la imagen aunque exista.
COPY herramientas.py agente.py api.py ./
COPY datos_personales/cv_denys.md ./datos_personales/
COPY static/ ./static/

# 4) Puerto: Cloud Run inyecta $PORT; en local cae a 8080.
ENV PORT=8080
EXPOSE 8080

# Arranque. --host 0.0.0.0 es OBLIGATORIO en contenedor (127.0.0.1 no se ve desde fuera).
# La API key de OpenAI y el APP_TOKEN llegan por ENTORNO (Secret Manager), nunca en la imagen.
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}"]
