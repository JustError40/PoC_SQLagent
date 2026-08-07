FROM python:3.10-slim

# Optional pip index mirror for networks where pypi.org is unreachable:
#   docker compose build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple api
ARG PIP_INDEX_URL=""
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY sqlagent ./sqlagent
COPY db_seed ./db_seed
RUN pip install --no-cache-dir --no-build-isolation .

COPY evals ./evals
COPY skills ./skills
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "sqlagent.web:app", "--host", "0.0.0.0", "--port", "8000"]
