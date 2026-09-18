FROM python:3.12-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home caller
COPY voice-gateway/gateway /app/gateway
USER caller
CMD ["uvicorn","gateway.main:app","--host","0.0.0.0","--port","8001","--no-access-log"]
