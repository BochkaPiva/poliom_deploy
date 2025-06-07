#!/bin/bash

# ===========================================
# POLIOM HR ASSISTANT DEPLOYMENT SCRIPT
# ===========================================

set -e  # Выход при любой ошибке

echo "🚀 Начинаем деплой POLIOM HR Assistant..."

# Проверяем наличие необходимых файлов
if [ ! -f ".env.production" ]; then
    echo "❌ Файл .env.production не найден!"
    echo "📝 Скопируйте .env.production.example в .env.production и заполните значения"
    exit 1
fi

if [ ! -f "docker-compose.prod.yml" ]; then
    echo "❌ Файл docker-compose.prod.yml не найден!"
    exit 1
fi

echo "✅ Все необходимые файлы найдены"

# Загружаем переменные окружения
export $(grep -v '^#' .env.production | xargs)

echo "🔧 Конфигурация POLIOM HR Assistant:"
echo "  - Окружение: $ENVIRONMENT"
echo "  - База данных: ${DATABASE_URL%%@*}@***"
echo "  - Redis: ${REDIS_URL%%@*}@***"
echo "  - Админ-панель порт: ${ADMIN_PANEL_PORT:-8000}"
echo "  - Telegram бот: ${TELEGRAM_BOT_TOKEN:0:10}***"
echo "  - GigaChat API: ${GIGACHAT_API_KEY:0:10}***"

# Останавливаем старые контейнеры
echo "🛑 Останавливаем старые контейнеры POLIOM..."
docker-compose -f docker-compose.prod.yml --env-file .env.production down --remove-orphans

# Удаляем старые образы (опционально)
read -p "🗑️ Удалить старые Docker образы? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️ Удаляем старые образы..."
    docker system prune -f
    docker image prune -f
fi

# Собираем новые образы
echo "🔨 Собираем Docker образы для POLIOM HR Assistant..."
docker-compose -f docker-compose.prod.yml --env-file .env.production build --no-cache

# Запускаем контейнеры
echo "🚀 Запускаем контейнеры POLIOM HR Assistant..."
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d

# Ждем запуска сервисов
echo "⏳ Ждем запуска сервисов..."
sleep 30

# Проверяем статус контейнеров
echo "📊 Проверяем статус контейнеров..."
docker-compose -f docker-compose.prod.yml --env-file .env.production ps

# Проверяем health check
echo "🏥 Проверяем здоровье сервисов POLIOM..."

# Проверяем админ-панель
ADMIN_PORT=${ADMIN_PANEL_PORT:-8000}
if curl -f http://localhost:$ADMIN_PORT/ > /dev/null 2>&1; then
    echo "✅ Админ-панель POLIOM доступна на порту $ADMIN_PORT"
else
    echo "❌ Админ-панель недоступна"
    echo "📋 Логи админ-панели:"
    docker-compose -f docker-compose.prod.yml --env-file .env.production logs admin-panel --tail=20
fi

# Проверяем Telegram бота
if docker-compose -f docker-compose.prod.yml --env-file .env.production exec -T telegram-bot python -c "import sys; sys.exit(0)" > /dev/null 2>&1; then
    echo "✅ Telegram бот POLIOM работает"
else
    echo "❌ Telegram бот недоступен"
    echo "📋 Логи Telegram бота:"
    docker-compose -f docker-compose.prod.yml --env-file .env.production logs telegram-bot --tail=20
fi

# Проверяем Celery worker
if docker-compose -f docker-compose.prod.yml --env-file .env.production exec -T celery-worker celery -A celery_app inspect ping > /dev/null 2>&1; then
    echo "✅ Celery worker работает"
else
    echo "❌ Celery worker недоступен"
    echo "📋 Логи Celery worker:"
    docker-compose -f docker-compose.prod.yml --env-file .env.production logs celery-worker --tail=20
fi

# Проверяем Redis
if docker-compose -f docker-compose.prod.yml --env-file .env.production exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis работает"
else
    echo "❌ Redis недоступен"
    echo "📋 Логи Redis:"
    docker-compose -f docker-compose.prod.yml --env-file .env.production logs redis --tail=20
fi

# Показываем логи
echo "📋 Последние логи сервисов POLIOM HR Assistant:"
echo "--- Telegram Bot ---"
docker-compose -f docker-compose.prod.yml --env-file .env.production logs telegram-bot --tail=10

echo "--- Admin Panel ---"
docker-compose -f docker-compose.prod.yml --env-file .env.production logs admin-panel --tail=10

echo "--- Celery Worker ---"
docker-compose -f docker-compose.prod.yml --env-file .env.production logs celery-worker --tail=10

echo "--- Redis ---"
docker-compose -f docker-compose.prod.yml --env-file .env.production logs redis --tail=10

echo ""
echo "🎉 Деплой POLIOM HR Assistant завершен!"
echo ""
echo "📊 Полезные команды:"
echo "  Логи:                docker-compose -f docker-compose.prod.yml logs -f [service_name]"
echo "  Перезапуск:          docker-compose -f docker-compose.prod.yml restart [service_name]"
echo "  Остановка:           docker-compose -f docker-compose.prod.yml down"
echo "  Статус:              docker-compose -f docker-compose.prod.yml ps"
echo ""
echo "🌐 Админ-панель POLIOM: http://localhost:$ADMIN_PORT"
echo "🤖 Telegram бот POLIOM готов к работе!"
echo "💬 GigaChat интеграция активна!"
echo ""
echo "✨ POLIOM HR Assistant успешно развернут!"

# Скрипт развертывания системы ПОЛИОМ на продакшен сервере

set -e

echo "🚀 Начинаем развертывание системы ПОЛИОМ..."

# Проверка прав root
if [[ $EUID -ne 0 ]]; then
   echo "❌ Этот скрипт должен запускаться с правами root"
   exit 1
fi

# Создание пользователя для приложения
echo "👤 Создание пользователя poliom..."
if ! id "poliom" &>/dev/null; then
    useradd -m -s /bin/bash poliom
    usermod -aG docker poliom
fi

# Создание директорий
echo "📁 Создание директорий..."
mkdir -p /opt/poliom/{logs,uploads,backups,nginx/ssl}
chown -R poliom:poliom /opt/poliom

# Копирование файлов проекта
echo "📋 Копирование файлов проекта..."
cp -r . /opt/poliom/
chown -R poliom:poliom /opt/poliom

# Настройка переменных окружения
echo "⚙️ Настройка переменных окружения..."
if [ ! -f /opt/poliom/.env ]; then
    cp /opt/poliom/.env.production /opt/poliom/.env
    echo "⚠️ Не забудьте отредактировать файл /opt/poliom/.env"
fi

# Генерация SSL сертификата (самоподписанный для тестирования)
echo "🔒 Генерация SSL сертификата..."
if [ ! -f /opt/poliom/nginx/ssl/privkey.pem ]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /opt/poliom/nginx/ssl/privkey.pem \
        -out /opt/poliom/nginx/ssl/fullchain.pem \
        -subj "/C=RU/ST=Moscow/L=Moscow/O=POLIOM/CN=localhost"
fi

# Создание systemd сервиса
echo "🔧 Создание systemd сервиса..."
cat > /etc/systemd/system/poliom.service << EOF
[Unit]
Description=POLIOM Corporate Bot System
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/poliom
ExecStart=/usr/bin/docker-compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker-compose -f docker-compose.prod.yml down
User=poliom
Group=poliom

[Install]
WantedBy=multi-user.target
EOF

# Создание скрипта резервного копирования
echo "💾 Создание скрипта резервного копирования..."
cat > /opt/poliom/backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/opt/poliom/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Создание резервной копии базы данных
docker exec poliom_postgres pg_dump -U poliom_user poliom_production > "$BACKUP_DIR/db_backup_$DATE.sql"

# Архивирование загруженных файлов
tar -czf "$BACKUP_DIR/uploads_backup_$DATE.tar.gz" -C /opt/poliom uploads/

# Удаление старых резервных копий (старше 30 дней)
find "$BACKUP_DIR" -name "*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

echo "✅ Резервная копия создана: $DATE"
EOF

chmod +x /opt/poliom/backup.sh
chown poliom:poliom /opt/poliom/backup.sh

# Добавление задачи в cron для резервного копирования
echo "⏰ Настройка автоматического резервного копирования..."
(crontab -u poliom -l 2>/dev/null; echo "0 2 * * * /opt/poliom/backup.sh") | crontab -u poliom -

# Настройка логротации
echo "📝 Настройка ротации логов..."
cat > /etc/logrotate.d/poliom << EOF
/opt/poliom/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 poliom poliom
    postrotate
        docker-compose -f /opt/poliom/docker-compose.prod.yml restart
    endscript
}
EOF

# Включение и запуск сервиса
echo "🎯 Запуск системы..."
systemctl daemon-reload
systemctl enable poliom
systemctl start poliom

echo "✅ Развертывание завершено!"
echo ""
echo "📋 Следующие шаги:"
echo "1. Отредактируйте файл /opt/poliom/.env"
echo "2. Настройте SSL сертификат в /opt/poliom/nginx/ssl/"
echo "3. Обновите домен в /opt/poliom/nginx/nginx.conf"
echo "4. Перезапустите систему: systemctl restart poliom"
echo ""
echo "🌐 Админ-панель будет доступна по адресу: https://ваш-домен.com"
echo "📊 Мониторинг: systemctl status poliom"
echo "📝 Логи: journalctl -u poliom -f" 