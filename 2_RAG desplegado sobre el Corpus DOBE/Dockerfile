# Dockerfile — receta de la imagen del RAG DOBE (Fase 4)
# =======================================================
# Construye una "caja" reproducible con Python + librerías + motor + API + frontend
# + corpus + índice. Se construye en la nube (Cloud Build, Fase 5); aquí solo la receta.

# 1) Imagen base: Python 3.13 "slim" (mínima, sin extras de SO que no usamos).
FROM python:3.13-slim

# Buenas prácticas de contenedor:
#   PYTHONDONTWRITEBYTECODE → no genera .pyc (imagen más limpia)
#   PYTHONUNBUFFERED        → logs salen en vivo (se ven en Cloud Run sin retraso)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 2) Dependencias PRIMERO (capa cacheable): si solo cambias código, no reinstala librerías.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Solo lo MÍNIMO para servir, nombrado explícitamente (lista blanca).
#    Al copiar solo estos ficheros, el .env NO puede colarse en la imagen aunque exista.
COPY rag_core.py api.py ./
COPY static/ ./static/
COPY corpus_dobe_enriquecido.json ./
COPY embeddings/indice_a.npy embeddings/indice_a.json ./embeddings/

# 4) Puerto: Cloud Run inyecta $PORT; en local cae a 8080 por defecto.
ENV PORT=8080
EXPOSE 8080

# Arranque. --host 0.0.0.0 es OBLIGATORIO en contenedor (127.0.0.1 no sería visible desde fuera).
# La clave OpenAI y el APP_TOKEN llegan por ENTORNO (Secret Manager en la nube), nunca en la imagen.
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}"]
