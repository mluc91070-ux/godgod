# Build context is the REPOSITORY ROOT, not backend/:
#
#   docker build -f backend/Dockerfile .
#
# The fixtures live outside backend/ and the image needs them, so the context
# has to cover both. docker-compose.yml and render.yaml both set it that way.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIXTURES_DIR=/data/fixtures

WORKDIR /app

COPY backend/requirements.txt backend/requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements-postgres.txt

COPY backend/ /app/
COPY data/ /data/

# Not root. The process only ever reads the fixtures and talks to the database.
RUN useradd --create-home --uid 10001 godgod && chown -R godgod:godgod /app /data
USER godgod

EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
