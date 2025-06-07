# 🚀 Руководство по развертыванию POLIOM на предприятии

## 📋 Что получает предприятие

### ✅ Готовый к развертыванию код:
- Исходный код системы
- Docker конфигурации
- Примеры .env файлов
- Документация и инструкции

### ❌ Что НЕ включено (создается на месте):
- Реальные токены и пароли
- Конфигурация сети
- SSL сертификаты
- Резервные копии

---

## 🔧 Алгоритм развертывания

### Этап 1: Подготовка сервера (IT-отдел)

```bash
# 1. Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 2. Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. Создание пользователя для приложения
sudo useradd -m -s /bin/bash poliom
sudo usermod -aG docker poliom
```

### Этап 2: Получение кода

```bash
# Переключение на пользователя приложения
sudo su - poliom

# Клонирование репозитория
git clone https://github.com/BochkaPiva/poliom_deploy.git
cd poliom_deploy
```

### Этап 3: Создание токенов

#### 3.1 Telegram Bot Token
```bash
# 1. Найти @BotFather в Telegram
# 2. Отправить /newbot
# 3. Следовать инструкциям
# 4. Скопировать токен (например: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)
```

#### 3.2 GigaChat API Key
```bash
# 1. Перейти на https://developers.sber.ru/gigachat
# 2. Зарегистрироваться
# 3. Создать приложение
# 4. Получить Client ID и Client Secret
```

### Этап 4: Конфигурация

#### 4.1 Создание .env файла
```bash
# Копирование примера
cp .env.example .env

# Редактирование конфигурации
nano .env
```

#### 4.2 Пример .env для предприятия
```env
# === ОСНОВНЫЕ НАСТРОЙКИ ===
# Telegram бот (от HR-отдела)
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# GigaChat API (от IT-отдела)
GIGACHAT_CLIENT_ID=ваш_client_id
GIGACHAT_CLIENT_SECRET=ваш_client_secret

# === БАЗА ДАННЫХ (генерируется IT) ===
POSTGRES_DB=poliom_production
POSTGRES_USER=poliom_user
POSTGRES_PASSWORD=СГЕНЕРИРОВАННЫЙ_СЛОЖНЫЙ_ПАРОЛЬ_32_СИМВОЛА
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# === БЕЗОПАСНОСТЬ (генерируется IT) ===
ADMIN_SECRET_KEY=СГЕНЕРИРОВАННЫЙ_КЛЮЧ_64_СИМВОЛА
JWT_SECRET_KEY=СГЕНЕРИРОВАННЫЙ_JWT_КЛЮЧ_64_СИМВОЛА

# === СЕТЬ (настраивается IT) ===
# Внутренний IP сервера
HOST_IP=192.168.1.100
ADMIN_PANEL_PORT=8001
PGADMIN_PORT=8082

# === ПРОИЗВОДСТВЕННЫЕ НАСТРОЙКИ ===
DEBUG=false
LOG_LEVEL=INFO
ENVIRONMENT=production

# === НАСТРОЙКИ RAG ===
SEARCH_LIMIT=15
SIMILARITY_THRESHOLD=0.3
MIN_SIMILARITY_THRESHOLD=0.25
```

### Этап 5: Генерация паролей (IT-отдел)

```bash
# Генерация сложных паролей
openssl rand -base64 32  # Для POSTGRES_PASSWORD
openssl rand -base64 48  # Для ADMIN_SECRET_KEY
openssl rand -base64 48  # Для JWT_SECRET_KEY

# Или использовать встроенный генератор
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Этап 6: Запуск системы

```bash
# Запуск в продакшн режиме
docker-compose -f docker-compose.prod.yml up -d

# Проверка статуса
docker-compose -f docker-compose.prod.yml ps

# Просмотр логов
docker-compose -f docker-compose.prod.yml logs -f
```

### Этап 7: Создание администратора

```bash
# Создание первого администратора
docker exec -it poliom_admin_panel python create_admin.py

# Ввести данные:
# Username: admin
# Email: admin@company.local
# Password: СЛОЖНЫЙ_ПАРОЛЬ
# Full Name: Системный администратор
```

---

## 🌐 Настройка сети

### Вариант 1: Локальная сеть (рекомендуется)

```bash
# Система доступна только внутри офиса
# Админ-панель: http://192.168.1.100:8001
# PgAdmin: http://192.168.1.100:8082
```

### Вариант 2: Внешний доступ (с осторожностью)

```bash
# Настройка Nginx с SSL
sudo apt install nginx certbot python3-certbot-nginx

# Создание конфигурации Nginx
sudo nano /etc/nginx/sites-available/poliom
```

#### Конфигурация Nginx:
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
# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/poliom /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Получение SSL сертификата
sudo certbot --nginx -d poliom.company.ru
```

---

## 🔒 Безопасность

### Обязательные меры:

1. **Файрвол**:
```bash
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow from 192.168.1.0/24 to any port 8001  # Только локальная сеть
```

2. **Регулярные обновления**:
```bash
# Автоматические обновления безопасности
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

3. **Мониторинг логов**:
```bash
# Настройка logrotate
sudo nano /etc/logrotate.d/poliom
```

4. **Резервное копирование**:
```bash
# Ежедневный бэкап БД
echo "0 2 * * * docker exec poliom_postgres pg_dump -U poliom_user poliom_production > /backup/poliom_$(date +\%Y\%m\%d).sql" | sudo crontab -
```

---

## 📊 Мониторинг

### Проверка здоровья системы:

```bash
# Скрипт проверки (создать check_health.sh)
#!/bin/bash
echo "=== POLIOM Health Check ==="
echo "Дата: $(date)"
echo ""

echo "1. Статус контейнеров:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "2. Использование ресурсов:"
docker stats --no-stream

echo ""
echo "3. Место на диске:"
df -h

echo ""
echo "4. Последние ошибки:"
docker-compose -f docker-compose.prod.yml logs --tail=10 | grep ERROR

echo ""
echo "5. Статус базы данных:"
docker exec poliom_postgres psql -U poliom_user -d poliom_production -c "SELECT COUNT(*) as documents FROM documents;"
```

### Автоматический мониторинг:
```bash
# Добавить в crontab для ежечасной проверки
echo "0 * * * * /home/poliom/poliom_deploy/check_health.sh >> /var/log/poliom_health.log" | sudo crontab -
```

---

## 🆘 Решение проблем

### Частые проблемы:

1. **Контейнер не запускается**:
```bash
docker-compose -f docker-compose.prod.yml logs имя_контейнера
```

2. **База данных недоступна**:
```bash
docker exec poliom_postgres pg_isready -U poliom_user
```

3. **Бот не отвечает**:
```bash
# Проверить токен
docker exec poliom_telegram_bot env | grep TELEGRAM_BOT_TOKEN
```

4. **Нет места на диске**:
```bash
# Очистка старых образов
docker system prune -a
```

---

## 📞 Поддержка

### Контакты для технической поддержки:
- **Документация**: папка `md_docs/`
- **Логи системы**: `docker-compose logs`
- **Проверка после перезагрузки**: `./check_after_reboot.sh`

### Регламент обслуживания:
- **Ежедневно**: проверка логов на ошибки
- **Еженедельно**: проверка места на диске
- **Ежемесячно**: обновление системы
- **Ежеквартально**: смена паролей

---

## ✅ Чек-лист развертывания

### Перед запуском:
- [ ] Docker установлен и работает
- [ ] Создан пользователь poliom
- [ ] Код скачан из репозитория
- [ ] Создан .env файл с уникальными паролями
- [ ] Получены токены Telegram и GigaChat
- [ ] Настроен файрвол
- [ ] Настроено резервное копирование

### После запуска:
- [ ] Все контейнеры запущены
- [ ] Админ-панель доступна
- [ ] Создан первый администратор
- [ ] Бот отвечает в Telegram
- [ ] Загружен тестовый документ
- [ ] Настроен мониторинг
- [ ] Проведено обучение пользователей

---

**Время развертывания: 2-4 часа (в зависимости от опыта IT-отдела)** 