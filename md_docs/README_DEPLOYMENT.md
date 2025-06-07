# 🏢 Руководство по развертыванию системы ПОЛИОМ

## 📋 Обзор системы

Корпоративная система ПОЛИОМ включает:
- 🤖 **Telegram-бот** для сотрудников
- 🔧 **Админ-панель** для управления контентом
- 📚 **База знаний** с поиском по документам
- ❓ **FAQ система** с возможностью редактирования

## 🏗️ Архитектура

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │   Admin Panel   │    │     Nginx       │
│   (Port 8080)   │    │   (Port 8001)   │    │  (Ports 80/443) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
         ┌─────────────────┐    ┌─────────────────┐
         │   PostgreSQL    │    │     Redis       │
         │   (Port 5432)   │    │   (Port 6379)   │
         └─────────────────┘    └─────────────────┘
```

## 🔧 Системные требования

### Минимальные требования:
- **ОС**: Ubuntu 20.04+ / CentOS 7+ / Windows Server 2019+
- **RAM**: 8GB (рекомендуется 16GB+)
- **CPU**: 4 ядра (рекомендуется 8+)
- **Диск**: 100GB SSD (рекомендуется 500GB+)
- **Сеть**: стабильное интернет-соединение

### Рекомендуемые требования для предприятия:
- **RAM**: 32GB
- **CPU**: 16 ядер
- **Диск**: 1TB NVMe SSD
- **Сеть**: выделенный канал 100 Мбит/с

## 🚀 Быстрое развертывание

### 1. Подготовка сервера (Ubuntu/CentOS)

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Установка Nginx
sudo apt install nginx -y
```

### 2. Загрузка и настройка проекта

```bash
# Клонирование проекта
git clone <ваш-репозиторий> /opt/poliom
cd /opt/poliom

# Настройка прав
sudo chown -R $USER:$USER /opt/poliom
chmod +x deploy.sh

# Запуск автоматического развертывания
sudo ./deploy.sh
```

### 3. Настройка переменных окружения

Отредактируйте файл `/opt/poliom/.env`:

```bash
sudo nano /opt/poliom/.env
```

**Обязательные параметры для изменения:**
- `POSTGRES_PASSWORD` - сильный пароль для БД
- `REDIS_PASSWORD` - пароль для Redis
- `SECRET_KEY` - секретный ключ (64+ символов)
- `ADMIN_PASSWORD` - пароль администратора
- `TELEGRAM_BOT_TOKEN` - токен от @BotFather
- `DOMAIN` - ваш домен

### 4. Получение SSL сертификата

#### Вариант A: Let's Encrypt (бесплатный)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d ваш-домен.com
```

#### Вариант B: Корпоративный сертификат
Поместите файлы сертификата в `/opt/poliom/nginx/ssl/`:
- `fullchain.pem` - полная цепочка сертификатов
- `privkey.pem` - приватный ключ

### 5. Запуск системы

```bash
# Перезапуск с новыми настройками
sudo systemctl restart poliom

# Проверка статуса
sudo systemctl status poliom
```

## 🔐 Безопасность

### Настройка файрвола
```bash
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable
```

### Настройка резервного копирования
Система автоматически создает резервные копии:
- **База данных**: ежедневно в 2:00
- **Файлы**: архивирование загруженных документов
- **Хранение**: 30 дней

Ручное создание резервной копии:
```bash
sudo -u poliom /opt/poliom/backup.sh
```

### Мониторинг безопасности
```bash
# Просмотр логов доступа
sudo tail -f /opt/poliom/logs/nginx/access.log

# Мониторинг системы
sudo systemctl status poliom
sudo docker ps
```

## 📊 Мониторинг и обслуживание

### Команды управления
```bash
# Статус системы
sudo systemctl status poliom

# Перезапуск
sudo systemctl restart poliom

# Остановка
sudo systemctl stop poliom

# Просмотр логов
sudo journalctl -u poliom -f

# Логи контейнеров
sudo docker logs poliom_admin_panel
sudo docker logs poliom_telegram_bot
```

### Обновление системы
```bash
cd /opt/poliom
git pull origin main
sudo docker-compose -f docker-compose.prod.yml build --no-cache
sudo systemctl restart poliom
```

### Масштабирование
Для увеличения производительности:

```yaml
# В docker-compose.prod.yml
celery-worker:
  deploy:
    replicas: 4  # Увеличить количество воркеров

postgres:
  environment:
    - POSTGRES_SHARED_BUFFERS=256MB
    - POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
```

## 🔧 Настройка Telegram бота

### 1. Создание бота
1. Напишите @BotFather в Telegram
2. Выполните команду `/newbot`
3. Укажите имя: `ПОЛИОМ | бот-справочник`
4. Укажите username: `poliom_helper_bot`
5. Сохраните полученный токен

### 2. Настройка webhook (опционально)
```bash
curl -X POST "https://api.telegram.org/bot<ВАШ_ТОКЕН>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://ваш-домен.com/webhook"}'
```

## 📱 Первоначальная настройка

### 1. Доступ к админ-панели
- URL: `https://ваш-домен.com`
- Логин: `admin` (или из .env)
- Пароль: из файла `.env`

### 2. Загрузка документов
1. Войдите в админ-панель
2. Перейдите в раздел "Документы"
3. Загрузите корпоративные документы
4. Дождитесь обработки

### 3. Настройка FAQ
1. Перейдите в "FAQ Меню"
2. Создайте разделы (например: "Отпуска", "Зарплата")
3. Добавьте вопросы и ответы

### 4. Тестирование бота
1. Найдите бота в Telegram: `@poliom_helper_bot`
2. Отправьте `/start`
3. Протестируйте поиск и FAQ

## 🆘 Устранение неполадок

### Проблема: Контейнеры не запускаются
```bash
# Проверка логов
sudo docker-compose -f docker-compose.prod.yml logs

# Проверка ресурсов
df -h
free -h
```

### Проблема: Бот не отвечает
```bash
# Проверка логов бота
sudo docker logs poliom_telegram_bot

# Проверка токена
curl "https://api.telegram.org/bot<ТОКЕН>/getMe"
```

### Проблема: Админ-панель недоступна
```bash
# Проверка Nginx
sudo nginx -t
sudo systemctl status nginx

# Проверка SSL
sudo certbot certificates
```

## 📞 Поддержка

### Контакты для технической поддержки:
- **Email**: tech-support@ваша-компания.com
- **Telegram**: @ваш_техподдержка_бот

### Документация:
- **API**: `/docs` в админ-панели
- **Логи**: `/opt/poliom/logs/`
- **Конфигурация**: `/opt/poliom/.env`

## 📈 Рекомендации по эксплуатации

### Ежедневно:
- Проверка статуса системы
- Мониторинг использования ресурсов

### Еженедельно:
- Проверка резервных копий
- Анализ логов на ошибки

### Ежемесячно:
- Обновление системы
- Проверка безопасности
- Анализ статистики использования

---

**🎯 Система готова к эксплуатации на предприятии ПОЛИОМ!** 