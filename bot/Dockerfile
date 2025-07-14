# Этап 1: Build-образ со всеми dev-зависимостями
FROM python:3.13-slim AS builder

WORKDIR /build

# Устанавливаем необходимые dev-пакеты
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY ./ ./bot/

# Устанавливаем зависимости в отдельную директорию
RUN pip install --prefix=/install -r bot/requirements.txt


# Этап 2: Финальный "чистый" образ
FROM python:3.13-slim

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /chat_mix_bot

# Копируем установленные зависимости из build-образа
COPY --from=builder /install /usr/local
COPY ./ ./bot/

CMD ["python3", "-m", "bot"]
