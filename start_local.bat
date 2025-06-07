@echo off
echo ========================================
echo    ЗАПУСК СИСТЕМЫ ПОЛИОМ (ЛОКАЛЬНО)
echo ========================================
echo.

REM Проверка наличия Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ОШИБКА: Docker не найден!
    echo Установите Docker Desktop с https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

echo ✅ Docker найден
echo.

REM Проверка файла переменных окружения
if not exist ".env.local" (
    echo ОШИБКА: Файл .env.local не найден!
    echo Скопируйте .env.local.example в .env.local и заполните TELEGRAM_BOT_TOKEN
    pause
    exit /b 1
)

echo ✅ Файл конфигурации найден
echo.

REM Остановка старых контейнеров
echo 🛑 Остановка старых контейнеров...
docker-compose -f docker-compose.local.yml --env-file .env.local down --remove-orphans

echo.
echo 🔨 Сборка и запуск системы...
echo Это может занять 10-15 минут при первом запуске...
echo.

REM Запуск системы
docker-compose -f docker-compose.local.yml --env-file .env.local up -d --build

echo.
echo ⏳ Ожидание запуска сервисов...
timeout /t 30 /nobreak >nul

echo.
echo 📊 Проверка статуса контейнеров...
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo.
echo ========================================
echo           СИСТЕМА ЗАПУЩЕНА!
echo ========================================
echo.

REM Определение IP адреса
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        set LOCAL_IP=%%b
        goto :found_ip
    )
)
:found_ip

echo 🌐 Админ-панель: http://%LOCAL_IP%:8001
echo    Логин: admin
echo    Пароль: admin123
echo.
echo 🗄️ PgAdmin: http://%LOCAL_IP%:8082
echo    Email: admin@poliom.local
echo    Пароль: admin123
echo.
echo 🤖 Telegram бот готов к работе!
echo.
echo 📋 Полезные команды:
echo    Остановить: docker-compose -f docker-compose.local.yml down
echo    Перезапустить: docker-compose -f docker-compose.local.yml restart
echo    Логи: docker-compose -f docker-compose.local.yml logs -f
echo.
echo Нажмите любую клавишу для выхода...
pause >nul 