# Руководство по развертыванию системы POLIOM

## Обзор

Данное руководство описывает процесс безопасного развертывания системы POLIOM с учетом всех необходимых проверок и мер предосторожности.

## Предварительные требования

### Системные требования
- Docker 20.10+
- Docker Compose 2.0+
- Минимум 10GB свободного места на диске
- 4GB RAM (рекомендуется 8GB)

### Обязательные переменные окружения
Создайте файл `.env.local` со следующими переменными:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# GigaChat API
GIGACHAT_API_KEY=your_gigachat_api_key

# Опциональные переменные
POSTGRES_PASSWORD=your_secure_password
REDIS_PASSWORD=your_redis_password
```

## Быстрый старт

### 1. Автоматическое развертывание (рекомендуется)

```bash
# Сделать скрипт исполняемым
chmod +x scripts/deploy.sh

# Запустить развертывание
./scripts/deploy.sh
```

Скрипт автоматически:
- Проверит системные требования
- Создаст резервные копии (если есть данные)
- Развернет все сервисы
- Проверит готовность системы

### 2. Ручное развертывание

Если автоматический скрипт не подходит:

```bash
# 1. Остановить существующие контейнеры
docker-compose -f docker-compose.local.yml down

# 2. Создать необходимые директории
mkdir -p docker/postgres uploads

# 3. Запустить сервисы
docker-compose -f docker-compose.local.yml up -d --build

# 4. Проверить статус
docker-compose -f docker-compose.local.yml ps

# 5. Проверить логи
docker-compose -f docker-compose.local.yml logs -f
```

## Проверка готовности системы

### Автоматическая проверка

```bash
python scripts/check_system.py
```

### Ручная проверка

1. **PostgreSQL и pgvector:**
```bash
docker exec poliom_postgres_local psql -U postgres -d poliom -c "SELECT version();"
docker exec poliom_postgres_local psql -U postgres -d poliom -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

2. **Health endpoints:**
```bash
curl http://localhost:8001/health
```

3. **Статус контейнеров:**
```bash
docker-compose -f docker-compose.local.yml ps
```

## Устранение проблем

### Проблема с pgvector

**Симптомы:**
- Ошибка "extension 'vector' does not exist"
- Проблемы с векторным поиском

**Решение:**
1. Убедитесь, что используется правильный образ PostgreSQL:
```yaml
# В docker-compose.local.yml
postgres:
  image: pgvector/pgvector:pg15  # НЕ postgres:15-alpine
```

2. Проверьте наличие инициализационного скрипта:
```bash
ls -la docker/postgres/init.sql
```

3. Пересоздайте контейнер PostgreSQL:
```bash
docker-compose -f docker-compose.local.yml down postgres
docker volume rm poliom_postgres_data_local
docker-compose -f docker-compose.local.yml up -d postgres
```

### Проблемы с памятью

**Симптомы:**
- Контейнеры завершаются с ошибкой OOM
- Медленная работа системы

**Решение:**
1. Увеличьте лимиты памяти в docker-compose.yml
2. Закройте ненужные приложения
3. Рассмотрите возможность использования swap

### Проблемы с портами

**Симптомы:**
- Ошибка "port already in use"

**Решение:**
1. Найдите процесс, использующий порт:
```bash
# Windows
netstat -ano | findstr :8001

# Linux/Mac
lsof -i :8001
```

2. Остановите процесс или измените порт в docker-compose.yml

## Резервное копирование

### Автоматическое резервное копирование

Скрипт развертывания автоматически создает резервные копии перед обновлением.

### Ручное резервное копирование

```bash
# Создать директорию для бэкапов
mkdir -p backups

# Бэкап базы данных
docker exec poliom_postgres_local pg_dump -U postgres poliom > backups/database_$(date +%Y%m%d_%H%M%S).sql

# Бэкап файлов
tar -czf backups/uploads_$(date +%Y%m%d_%H%M%S).tar.gz uploads/
```

### Восстановление из резервной копии

```bash
# Восстановление базы данных
docker exec -i poliom_postgres_local psql -U postgres poliom < backups/database_YYYYMMDD_HHMMSS.sql

# Восстановление файлов
tar -xzf backups/uploads_YYYYMMDD_HHMMSS.tar.gz
```

## Мониторинг

### Проверка логов

```bash
# Все сервисы
docker-compose -f docker-compose.local.yml logs -f

# Конкретный сервис
docker-compose -f docker-compose.local.yml logs -f admin-panel
docker-compose -f docker-compose.local.yml logs -f telegram-bot
docker-compose -f docker-compose.local.yml logs -f celery-worker
```

### Мониторинг ресурсов

```bash
# Использование ресурсов контейнерами
docker stats

# Использование дискового пространства
docker system df
```

## Обновление системы

### Безопасное обновление

1. Создайте резервную копию:
```bash
./scripts/backup.sh  # если есть такой скрипт
```

2. Получите последние изменения:
```bash
git pull origin main
```

3. Запустите развертывание:
```bash
./scripts/deploy.sh
```

### Откат к предыдущей версии

```bash
# Остановить текущие контейнеры
docker-compose -f docker-compose.local.yml down

# Восстановить из резервной копии
# (см. раздел "Восстановление из резервной копии")

# Запустить предыдущую версию
git checkout previous_commit_hash
./scripts/deploy.sh
```

## Производственное развертывание

### Дополнительные меры безопасности

1. **Измените пароли по умолчанию:**
```bash
# В .env.local
POSTGRES_PASSWORD=strong_random_password
ADMIN_PASSWORD=strong_admin_password
```

2. **Настройте HTTPS:**
- Используйте reverse proxy (nginx, traefik)
- Получите SSL-сертификаты

3. **Настройте файрвол:**
```bash
# Разрешить только необходимые порты
ufw allow 80
ufw allow 443
ufw deny 8001  # Закрыть прямой доступ к админ-панели
```

4. **Настройте мониторинг:**
- Логирование в централизованную систему
- Алерты при сбоях
- Мониторинг производительности

### Переменные окружения для продакшена

```bash
# .env.production
NODE_ENV=production
DEBUG=false
LOG_LEVEL=info

# Безопасность
SECURE_COOKIES=true
CSRF_PROTECTION=true

# Производительность
WORKER_PROCESSES=4
MAX_CONNECTIONS=1000
```

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи контейнеров
2. Запустите скрипт диагностики: `python scripts/check_system.py`
3. Обратитесь к документации Docker и PostgreSQL
4. Создайте issue в репозитории проекта

## Полезные команды

```bash
# Полная очистка Docker (ОСТОРОЖНО!)
docker system prune -a --volumes -f

# Перезапуск конкретного сервиса
docker-compose -f docker-compose.local.yml restart admin-panel

# Выполнение команд в контейнере
docker exec -it poliom_postgres_local psql -U postgres -d poliom

# Просмотр использования ресурсов
docker stats --no-stream

# Экспорт/импорт образов
docker save -o poliom_backup.tar poliom_admin_panel:latest
docker load -i poliom_backup.tar
``` 