FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --timeout=120 --retries=5 --require-hashes --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app:create_app \
    APP_ENV=production
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=/wheels --require-hashes -r requirements.txt \
    && rm -rf /wheels \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app static ./static
COPY --chown=app:app pyproject.toml ./pyproject.toml
USER app:app
EXPOSE 5000
CMD ["python", "-m", "app.web_startup"]

