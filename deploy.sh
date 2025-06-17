#!/bin/bash

# Скрипт безопасного развертывания системы POLIOM
# Включает все необходимые проверки и валидации

set -e  # Остановка при любой ошибке

echo "🚀 Начало развертывания системы POLIOM"
echo "======================================"

# Функция логирования
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Функция проверки требований
check_requirements() {
    log "Проверка системных требований..."
    
    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        echo "❌ Docker не установлен!"
        exit 1
    fi
    log "✅ Docker найден: $(docker --version)"
    
    # Проверка Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ Docker Compose не установлен!"
        exit 1
    fi
    log "✅ Docker Compose найден: $(docker-compose --version)"
    
    # Проверка свободного места (минимум 10GB)
    available_space=$(df . | tail -1 | awk '{print $4}')
    if [ "$available_space" -lt 10485760 ]; then  # 10GB в KB
        echo "❌ Недостаточно свободного места! Требуется минимум 10GB"
        exit 1
    fi
    log "✅ Свободное место: $(df -h . | tail -1 | awk '{print $4}')"
}

# Функция проверки переменных окружения
check_env_vars() {
    log "Проверка переменных окружения..."
    
    required_vars=(
        "TELEGRAM_BOT_TOKEN"
        "GIGACHAT_API_KEY"
    )
    
    missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo "❌ Отсутствуют обязательные переменные окружения:"
        printf '  - %s\n' "${missing_vars[@]}"
        echo "Создайте файл .env.local с необходимыми переменными"
        exit 1
    fi
    
    log "✅ Все обязательные переменные окружения установлены"
}

# Функция создания резервной копии
backup_data() {
    if [ -d "backups" ]; then
        log "Создание резервной копии данных..."
        backup_dir="backups/backup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        # Бэкап базы данных если контейнер запущен
        if docker ps | grep -q poliom_postgres; then
            docker exec poliom_postgres_local pg_dump -U postgres poliom > "$backup_dir/database.sql"
            log "✅ Резервная копия базы данных создана"
        fi
        
        # Бэкап загруженных файлов
        if [ -d "uploads" ]; then
            cp -r uploads "$backup_dir/"
            log "✅ Резервная копия файлов создана"
        fi
    fi
}

# Функция развертывания
deploy() {
    log "Запуск развертывания..."
    
    # Остановка существующих контейнеров
    log "Остановка существующих контейнеров..."
    docker-compose -f docker-compose.local.yml down || true
    
    # Создание необходимых директорий
    log "Создание директорий..."
    mkdir -p docker/postgres uploads scripts
    
    # Запуск сервисов
    log "Запуск сервисов..."
    docker-compose -f docker-compose.local.yml up -d --build
    
    # Ожидание готовности PostgreSQL
    log "Ожидание готовности PostgreSQL..."
    max_attempts=30
    attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if docker exec poliom_postgres_local pg_isready -U postgres > /dev/null 2>&1; then
            log "✅ PostgreSQL готов"
            break
        fi
        
        attempt=$((attempt + 1))
        log "Попытка $attempt/$max_attempts..."
        sleep 2
    done
    
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ PostgreSQL не запустился в течение 60 секунд"
        exit 1
    fi
    
    # Проверка pgvector
    log "Проверка расширения pgvector..."
    if docker exec poliom_postgres_local psql -U postgres -d poliom -c "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');" | grep -q "t"; then
        log "✅ Расширение pgvector установлено"
    else
        echo "❌ Расширение pgvector не найдено!"
        exit 1
    fi
}

# Функция проверки готовности системы
verify_deployment() {
    log "Проверка готовности системы..."
    
    # Ожидание запуска всех сервисов
    sleep 30
    
    # Проверка health endpoints
    services=(
        "http://localhost:8001/health:Админ-панель"
    )
    
    for service in "${services[@]}"; do
        url="${service%:*}"
        name="${service#*:}"
        
        log "Проверка $name ($url)..."
        
        max_attempts=10
        attempt=0
        
        while [ $attempt -lt $max_attempts ]; do
            if curl -f -s "$url" > /dev/null 2>&1; then
                log "✅ $name готов"
                break
            fi
            
            attempt=$((attempt + 1))
            sleep 3
        done
        
        if [ $attempt -eq $max_attempts ]; then
            echo "❌ $name не отвечает"
            exit 1
        fi
    done
    
    # Проверка статуса контейнеров
    log "Проверка статуса контейнеров..."
    if docker-compose -f docker-compose.local.yml ps | grep -q "unhealthy\|Exit"; then
        echo "❌ Некоторые контейнеры не работают корректно:"
        docker-compose -f docker-compose.local.yml ps
        exit 1
    fi
    
    log "✅ Все контейнеры работают корректно"
}

# Основная функция
main() {
    # Загрузка переменных окружения
    if [ -f ".env.local" ]; then
        export $(cat .env.local | grep -v '^#' | xargs)
    fi
    
    check_requirements
    check_env_vars
    backup_data
    deploy
    verify_deployment
    
    echo ""
    echo "🎉 РАЗВЕРТЫВАНИЕ ЗАВЕРШЕНО УСПЕШНО!"
    echo "======================================"
    echo "Админ-панель: http://localhost:8001"
    echo "PgAdmin: http://localhost:8082"
    echo "Логин админ-панели: admin / poliom_\$487%0_admin"
    echo ""
    echo "Для проверки логов используйте:"
    echo "  docker-compose -f docker-compose.local.yml logs -f"
    echo ""
}

# Обработка сигналов
trap 'echo "❌ Развертывание прервано"; exit 1' INT TERM

# Запуск
main "$@" 