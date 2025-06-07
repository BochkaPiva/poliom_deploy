# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements.txt
COPY services/telegram-bot/requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY services/telegram-bot/ .

# Копируем shared модули
COPY services/shared/ /app/shared/

# Создаем директории для логов, кэша и моделей
RUN mkdir -p logs cache models_cache uploads

# Создаем пользователя для безопасности
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Устанавливаем переменные окружения
ENV PYTHONPATH=/app:/app/shared
ENV PYTHONUNBUFFERED=1

# Открываем порт для health check
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Запускаем бота
CMD ["python", "main.py"] 