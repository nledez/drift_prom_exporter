ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.10.2

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS build

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY main.py ./
RUN uv sync --frozen

FROM python:${PYTHON_VERSION}-slim-bookworm

WORKDIR /app

COPY --from=build /app/.venv /app/.venv
COPY main.py VERSION ./

ENV PATH="/app/.venv/bin:$PATH"

ENV PORT=8000
EXPOSE ${PORT}
CMD [ "python", "main.py" ]
