# syntax=docker/dockerfile:1
# Pin: python:3.12-slim (bookworm). Digest recorded in CI buildx provenance.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="threadforge" \
      threadforge.python_base="python:3.12-slim"
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY fixtures ./fixtures
COPY scripts ./scripts
COPY agent ./agent
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY openapi.json ./openapi.json
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -e ".[all]" \
 && python -c "import threadforge; print(threadforge.__file__)"
ENV TF_DATA=/data
EXPOSE 8000
CMD ["uvicorn", "threadforge.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
