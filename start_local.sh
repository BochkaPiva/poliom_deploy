#!/bin/bash

echo "========================================"
echo "   ЗАПУСК СИСТЕМЫ ПОЛИОМ (ЛОКАЛЬНО)"
echo "========================================"
echo

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo "❌ ОШИБКА: Docker не найден!"
    echo "Установите Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "✅ Docker найден"
echo

# Проверка наличия Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ ОШИБКА: Docker Compose не найден!"
    echo "Установите Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker Compose найден"
echo

# Проверка файла переменных окружения
if [ ! -f ".env.local" ]; then
    echo "❌ ОШИБКА: Файл .env.local не найден!"
    echo "Скопируйте .env.example в .env.local и заполните TELEGRAM_BOT_TOKEN"
    exit 1
fi

echo "✅ Файл конфигурации найден"
echo

# Остановка старых контейнеров
echo "🛑 Остановка старых контейнеров..."
docker-compose -f docker-compose.local.yml --env-file .env.local down --remove-orphans

echo
echo "🔨 Сборка и запуск системы..."
echo "Это может занять 10-15 минут при первом запуске..."
echo

# Запуск системы
docker-compose -f docker-compose.local.yml --env-file .env.local up -d --build

echo
echo "⏳ Ожидание запуска сервисов..."
sleep 30

echo
echo "📊 Проверка статуса контейнеров..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo
echo "========================================"
echo "          СИСТЕМА ЗАПУЩЕНА!"
echo "========================================"
echo

# Определение IP адреса
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "🌐 Админ-панель: http://$LOCAL_IP:8001"
echo "   Логин: admin"
echo "   Пароль: admin123"
echo
echo "🗄️ PgAdmin: http://$LOCAL_IP:8082"
echo "   Email: admin@poliom.local"
echo "   Пароль: admin123"
echo
echo "🤖 Telegram бот готов к работе!"
echo
echo "📋 Полезные команды:"
echo "   Остановить: docker-compose -f docker-compose.local.yml down"
echo "   Перезапустить: docker-compose -f docker-compose.local.yml restart"
echo "   Логи: docker-compose -f docker-compose.local.yml logs -f"
echo
echo "Нажмите Enter для выхода..."
read 