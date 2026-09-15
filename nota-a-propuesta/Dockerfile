FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run inyecta PORT (por defecto 8080) y espera que el contenedor escuche ahí.
ENV PORT=8080
EXPOSE 8080

# gunicorn en vez del servidor de desarrollo de Flask. 1 worker: el dashboard
# de "revisión en curso" (DRAFTS) vive en memoria de proceso — con más de un
# worker/instancia, una request podría caer en un proceso que no tiene ese
# borrador. El histórico del dashboard (Firestore) no depende de esto.
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120 app:app
