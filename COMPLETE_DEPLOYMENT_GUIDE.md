# 🚀 Полное руководство по развертыванию системы POLIOM

## 📋 Обзор системы

**POLIOM** - корпоративная система чат-бота для HR-отделов, включающая:
- 🤖 **Telegram-бот** для сотрудников с умным поиском по документам
- 🔧 **Админ-панель** для управления контентом и FAQ
- 📚 **База знаний** с векторным поиском по документам
- ❓ **FAQ система** с возможностью редактирования
- 🔍 **RAG (Retrieval-Augmented Generation)** для точных ответов

---

## ⚡ Быстрый старт (5 минут)

### 📋 Что нужно:
1. **Docker Desktop** (установлен)
2. **Telegram бот токен** (от @BotFather)
3. **10GB свободного места**

### 🚀 Запуск:
1. **Windows**: Дважды кликните `start_local.bat`
2. **Linux/macOS**: Выполните `./start_local.sh`
3. **Дождитесь** завершения (10-15 минут при первом запуске)

### 🌐 Доступ:
- **Админ-панель**: `http://ВАШ_IP:8001` (admin/admin123)
- **PgAdmin**: `http://ВАШ_IP:8082` (admin@poliom.local/admin123)
- **Telegram бот**: Найдите в Telegram по username

---

## 🏗️ Архитектура системы

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │   Admin Panel   │    │   Celery Worker │
│   (Port 8080)   │    │   (Port 8001)   │    │  (Background)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌─────────────────┐    ┌─────────────────┐
         │ PostgreSQL+pgvector │    │     Redis       │
         │   (Port 5432)   │    │   (Port 6379)   │
         └─────────────────┘    └─────────────────┘
```

---

## 🔧 Системные требования

### Минимальные (для тестирования):
- **ОС**: Windows 10+ / Ubuntu 20.04+ / macOS 10.15+
- **RAM**: 8GB
- **CPU**: 4 ядра
- **Диск**: 50GB свободного места
- **Docker**: 20.10+

### Рекомендуемые (для предприятия):
- **RAM**: 16GB+
- **CPU**: 8+ ядер
- **Диск**: 200GB+ SSD
- **Сеть**: стабильное соединение

---

## 📦 Установка Docker

### Windows:
1. Скачайте: https://www.docker.com/products/docker-desktop/
2. Установите и перезагрузите компьютер
3. Запустите Docker Desktop
4. Проверьте: `docker --version`

### Linux (Ubuntu/CentOS):
```bash
# Автоматическая установка
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка для применения прав
sudo reboot
```

### macOS:
1. Установите через Homebrew: `brew install --cask docker`
2. Или скачайте с официального сайта
3. Запустите Docker Desktop

---

## 🤖 Создание Telegram бота

### Пошаговая инструкция:
1. Откройте **Telegram**
2. Найдите **@BotFather**
3. Отправьте: `/newbot`
4. Введите имя: `ПОЛИОМ HR Справочник`
5. Введите username: `poliom_hr_bot` (должен быть уникальным)
6. **Скопируйте токен**: `1234567890:ABCdefGHI...`
7. Сохраните токен - он понадобится для настройки

### Дополнительные настройки бота:
```
/setdescription - Корпоративный HR-бот для поиска информации по документам
/setabouttext - Умный помощник для сотрудников компании
/setuserpic - Загрузите логотип компании
```

---

## ⚙️ Конфигурация системы

### Локальная разработка (.env.local):
```env
# === TELEGRAM BOT ===
TELEGRAM_BOT_TOKEN=ВСТАВЬТЕ_СЮДА_ВАШ_ТОКЕН_ОТ_BOTFATHER

# === GIGACHAT API (опционально) ===
GIGACHAT_API_KEY=ВАША_GIGACHAT_API_KEY
GIGACHAT_SCOPE=GIGACHAT_API_PERS

# === БАЗА ДАННЫХ ===
POSTGRES_DB=poliom_local
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres123
DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/poliom_local

# === АДМИН ПАНЕЛЬ ===
SECRET_KEY=your-secret-key-here-make-it-long-and-random
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# === НАСТРОЙКИ СИСТЕМЫ ===
DEBUG=true
LOG_LEVEL=INFO
ENVIRONMENT=local
MAX_FILE_SIZE=50MB
```

### Продакшн (.env):
```env
# === БЕЗОПАСНОСТЬ ===
SECRET_KEY=СГЕНЕРИРОВАННЫЙ_КЛЮЧ_64_СИМВОЛА_МИНИМУМ
JWT_SECRET_KEY=ДРУГОЙ_СГЕНЕРИРОВАННЫЙ_КЛЮЧ_64_СИМВОЛА

# === БАЗА ДАННЫХ ===
POSTGRES_PASSWORD=СЛОЖНЫЙ_ПАРОЛЬ_32_СИМВОЛА
REDIS_PASSWORD=СЛОЖНЫЙ_ПАРОЛЬ_REDIS

# === СЕТЬ ===
DOMAIN=poliom.company.ru
HOST_IP=192.168.1.100
ADMIN_PANEL_PORT=8001

# === ПРОИЗВОДСТВО ===
DEBUG=false
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

---

## 🚀 Варианты развертывания

### 1. Локальная разработка

**Для тестирования и разработки:**

```bash
# Windows
start_local.bat

# Linux/macOS
./start_local.sh
```

**Доступ:**
- Админ-панель: `http://localhost:8001`
- PgAdmin: `http://localhost:8082`

### 2. Локальная сеть предприятия (рекомендуется)

**Преимущества:**
- ✅ Данные остаются в офисе
- ✅ Независимость от интернета
- ✅ Полный контроль доступа
- ✅ Стоимость: 0 рублей

**Развертывание:**
```bash
# Linux/macOS
sudo ./deploy.sh

# Windows Server
.\deploy.ps1
```

**Доступ:**
- Админ-панель: `http://192.168.1.XXX:8001`
- Доступ с любого компьютера в офисе

### 3. Облачное развертывание

**Для внешнего доступа:**

#### VK Cloud (Россия):
- Kubernetes: ~15,000₽/месяц
- PostgreSQL: ~8,000₽/месяц
- **Бонус**: 5,000₽ для новых пользователей

#### DigitalOcean:
- Droplet 4GB: $24/месяц
- PostgreSQL: $15/месяц
- **Бонус**: $200 на 60 дней

---

## 🔐 Безопасное развертывание на предприятии

### Этап 1: Подготовка сервера

```bash
# Создание пользователя для приложения
sudo useradd -m -s /bin/bash poliom
sudo usermod -aG docker poliom

# Создание директорий
sudo mkdir -p /opt/poliom/{logs,uploads,backups}
sudo chown -R poliom:poliom /opt/poliom
```

### Этап 2: Получение кода

```bash
# Переключение на пользователя приложения
sudo su - poliom

# Клонирование репозитория
git clone https://github.com/your-company/poliom.git /opt/poliom
cd /opt/poliom
```

### Этап 3: Генерация паролей

```bash
# Генерация сложных паролей
openssl rand -base64 32  # Для POSTGRES_PASSWORD
openssl rand -base64 48  # Для SECRET_KEY
openssl rand -base64 48  # Для JWT_SECRET_KEY

# Или Python генератор
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Этап 4: Настройка конфигурации

```bash
# Копирование примера
cp .env.example .env

# Редактирование (используйте nano, vim или другой редактор)
nano .env
```

### Этап 5: Запуск системы

```bash
# Автоматическое развертывание
./deploy.sh

# Или ручной запуск
docker-compose -f docker-compose.prod.yml up -d
```

### Этап 6: Создание администратора

```bash
# Создание первого администратора
docker exec -it poliom_admin_panel python create_admin.py
```

---

## 🌐 Настройка сети

### Внутренняя сеть (рекомендуется):

```bash
# Определение IP сервера
ip addr show  # Linux
ipconfig      # Windows

# Доступ с любого компьютера в офисе:
# http://192.168.1.XXX:8001
```

### Внешний доступ через Nginx:

```bash
# Установка Nginx
sudo apt install nginx certbot python3-certbot-nginx

# Конфигурация
sudo nano /etc/nginx/sites-available/poliom
```

**Конфигурация Nginx:**
```nginx
server {
    listen 80;
    server_name poliom.company.ru;
    
    location / {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Активация и SSL
sudo ln -s /etc/nginx/sites-available/poliom /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d poliom.company.ru
```

---

## 🛡️ Безопасность

### Настройка файрвола:
```bash
# Ubuntu/CentOS
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### Меры безопасности:
- 🔐 **Переменные окружения** - все ключи в .env файлах
- 🚫 **Непривилегированные контейнеры** - запуск без root
- 🔒 **HTTPS в продакшне** - SSL сертификаты
- ✅ **Валидация данных** - проверка всех входных данных
- ⏱️ **Rate limiting** - ограничение частоты запросов
- 📝 **Аудит действий** - логирование всех операций

---

## 📚 Использование системы

### 1. Загрузка документов:
1. Откройте админ-панель: `http://ВАШ_IP:8001`
2. Войдите: `admin` / `ваш_пароль`
3. Перейдите в **"Документы"** → **"Добавить документ"**
4. Загрузите PDF, DOCX или TXT файлы
5. Дождитесь обработки (статус "Завершено")

### 2. Создание FAQ:
1. В админ-панели перейдите в **"FAQ Меню"**
2. Создайте разделы (например: "Отпуска", "Зарплата", "Больничные")
3. Добавьте вопросы и ответы в каждый раздел
4. FAQ появится в боте как кнопки быстрого доступа

### 3. Использование бота:
- **Умный поиск**: просто напишите вопрос боту
- **FAQ меню**: используйте кнопки для быстрых ответов
- **Команды**: `/start`, `/help`, `/menu`

---

## 📊 Мониторинг и диагностика

### Проверка здоровья системы:
```bash
# Статус всех контейнеров
docker-compose ps

# Использование ресурсов
docker stats --no-stream

# Логи с ошибками
docker-compose logs | grep ERROR

# Проверка базы данных
docker exec poliom_postgres psql -U postgres -d poliom -c "SELECT COUNT(*) FROM documents;"
```

### Ключевые метрики:
- **Время ответа бота**: < 30 секунд
- **Использование RAM**: < 8 GB
- **Размер базы данных**: зависит от количества документов
- **Статус обработки документов**: в админ-панели

### Health endpoints:
```bash
# Проверка админ-панели
curl http://localhost:8001/health

# Проверка всех сервисов
python scripts/check_system.py
```

---

## 🆘 Решение проблем

### "Docker не найден":
```bash
# Установите Docker Desktop и перезагрузите компьютер
# Windows: https://www.docker.com/products/docker-desktop/
```

### "Бот не отвечает":
```bash
# Проверьте токен в .env файле
# Проверьте логи бота
docker logs poliom_telegram_bot --tail 20
```

### "Админ-панель недоступна":
```bash
# Проверьте IP адрес
ipconfig  # Windows
ip addr   # Linux

# Проверьте статус контейнера
docker ps | grep admin-panel
```

### "Документы не обрабатываются":
```bash
# Проверьте Celery worker
docker logs poliom_celery_worker --tail 20

# Перезапустите обработку
docker-compose restart celery-worker
```

### "Ошибки pgvector":
```bash
# Проверьте расширение
docker exec poliom_postgres psql -U postgres -d poliom -c "SELECT * FROM pg_extension WHERE extname = 'vector';"

# Пересоздайте базу данных
docker-compose down postgres
docker volume rm poliom_postgres_data
docker-compose up -d postgres
```

---

## 💾 Резервное копирование

### Автоматическое резервное копирование:
Система автоматически создает резервные копии:
- **База данных**: ежедневно в 2:00
- **Файлы**: архивирование загруженных документов
- **Хранение**: 30 дней

### Ручное резервное копирование:
```bash
# Создать директорию для бэкапов
mkdir -p backups

# Бэкап базы данных
docker exec poliom_postgres pg_dump -U postgres poliom > backups/database_$(date +%Y%m%d_%H%M%S).sql

# Бэкап файлов
tar -czf backups/uploads_$(date +%Y%m%d_%H%M%S).tar.gz uploads/
```

### Восстановление:
```bash
# Восстановление базы данных
docker exec -i poliom_postgres psql -U postgres poliom < backups/database_YYYYMMDD_HHMMSS.sql

# Восстановление файлов
tar -xzf backups/uploads_YYYYMMDD_HHMMSS.tar.gz
```

---

## 🔄 Обновление системы

### Обновление кода:
```bash
# Остановите систему
docker-compose down

# Обновите код (git pull или замените файлы)
git pull origin main

# Пересоберите образы
docker-compose build --no-cache

# Запустите систему
docker-compose up -d
```

### Обновление зависимостей:
```bash
# Обновите requirements.txt
# Пересоберите образы
docker-compose build --no-cache
```

---

## 📈 Масштабирование

### Увеличение производительности:
1. **Больше RAM**: увеличьте лимиты в docker-compose.yml
2. **Больше workers**: увеличьте количество Celery workers
3. **SSD диск**: для быстрой работы с базой данных
4. **Кэширование**: Redis уже настроен для кэширования

### Горизонтальное масштабирование:
```yaml
# В docker-compose.yml
celery-worker:
  deploy:
    replicas: 4  # Увеличить количество воркеров

postgres:
  environment:
    - POSTGRES_SHARED_BUFFERS=256MB
    - POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
```

---

## 🚀 Доступные скрипты

### Локальная разработка:
- **`start_local.bat`** - Запуск системы на Windows (локально)
- **`start_local.sh`** - Запуск системы на Linux/macOS (локально)

### Продакшн развертывание:
- **`deploy.sh`** - Безопасное развертывание на Linux/macOS сервере
- **`deploy.ps1`** - Развертывание на Windows Server

### Дополнительные утилиты:
- **`scripts/check_system.py`** - Python скрипт диагностики системы

---

## 📞 Поддержка и развитие

### Логирование:
- Все действия логируются в базу данных
- Логи Docker контейнеров доступны через `docker logs`
- Структурированные логи в JSON формате

### Полезные команды:
```bash
# Статус системы
docker-compose ps

# Перезапуск сервиса
docker-compose restart [service_name]

# Просмотр логов
docker-compose logs -f [service_name]

# Остановка системы
docker-compose down

# Полная очистка (ОСТОРОЖНО!)
docker-compose down -v
docker system prune -a
```

---

## ✅ Чек-лист развертывания

### Перед развертыванием:
- [ ] Docker установлен и работает
- [ ] Создан Telegram бот и получен токен
- [ ] Настроен .env файл с правильными значениями
- [ ] Проверено свободное место на диске (минимум 10GB)
- [ ] Настроены права доступа к файлам

### После развертывания:
- [ ] Все контейнеры запущены (`docker ps`)
- [ ] Админ-панель доступна по IP:8001
- [ ] Telegram бот отвечает на команды
- [ ] Загружен тестовый документ
- [ ] Создан тестовый FAQ
- [ ] Настроено резервное копирование
- [ ] Проинформированы сотрудники

### Безопасность:
- [ ] Изменены пароли по умолчанию
- [ ] Настроен файрвол
- [ ] SSL сертификат установлен (для внешнего доступа)
- [ ] Логирование настроено
- [ ] Мониторинг работает

---

## 🎯 Заключение

**Система POLIOM готова к работе!**

- ✅ Telegram бот отвечает на вопросы сотрудников
- ✅ Админ-панель для управления контентом
- ✅ База данных для хранения документов
- ✅ FAQ система для частых вопросов
- ✅ Векторный поиск для точных ответов
- ✅ Безопасное развертывание на предприятии

**Время на настройку: 15-30 минут** ⚡

**Удачного использования! 🚀** 