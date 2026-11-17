FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    ANONYMIZED_TELEMETRY=False

RUN useradd --create-home --uid 10001 app

COPY pyproject.toml README.md LICENSE ./
COPY booking_agent ./booking_agent
COPY knowledge ./knowledge
COPY static ./static
COPY entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir . \
    && chmod +x /entrypoint.sh \
    && mkdir -p /data/chroma \
    && chown -R app:app /data

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
