FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY tapes/ tapes/
RUN uv sync --frozen --no-dev

EXPOSE 8080

ENTRYPOINT ["uv", "run", "tapes"]
CMD ["--serve", "--auto-commit"]
