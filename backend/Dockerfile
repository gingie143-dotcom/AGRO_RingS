FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client-17 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home caller && mkdir /backups && chown caller:caller /backups
COPY backend/ /app/
USER caller
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-access-log"]
