# POLIOM HR Assistant - Docker Management
.DEFAULT_GOAL := help

# Переменные
COMPOSE_FILE := docker-compose.yml
COMPOSE_PROD_FILE := docker-compose.prod.yml
PROJECT_NAME := poliom-hr-assistant

# Цвета для вывода
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help build up down restart logs clean dev prod status health

help: ## Показать справку
	@echo "$(BLUE)POLIOM HR Assistant - Docker Management$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

# Команды для разработки
build: ## Собрать все образы
	@echo "$(YELLOW)Сборка Docker образов...$(NC)"
	docker-compose -f $(COMPOSE_FILE) build

up: ## Запустить все сервисы в режиме разработки
	@echo "$(GREEN)Запуск сервисов в режиме разработки...$(NC)"
	docker-compose -f $(COMPOSE_FILE) up -d
	@echo "$(GREEN)Сервисы запущены!$(NC)"
	@echo "$(BLUE)Админ-панель: http://localhost:8001$(NC)"
	@echo "$(BLUE)pgAdmin: http://localhost:8080$(NC)"

down: ## Остановить все сервисы
	@echo "$(RED)Остановка сервисов...$(NC)"
	docker-compose -f $(COMPOSE_FILE) down

restart: ## Перезапустить все сервисы
	@echo "$(YELLOW)Перезапуск сервисов...$(NC)"
	docker-compose -f $(COMPOSE_FILE) restart

logs: ## Показать логи всех сервисов
	docker-compose -f $(COMPOSE_FILE) logs -f

logs-bot: ## Показать логи телеграм-бота
	docker-compose -f $(COMPOSE_FILE) logs -f telegram-bot

logs-admin: ## Показать логи админ-панели
	docker-compose -f $(COMPOSE_FILE) logs -f admin-panel

logs-celery: ## Показать логи Celery worker
	docker-compose -f $(COMPOSE_FILE) logs -f celery-worker

# Команды для продакшена
prod-build: ## Собрать образы для продакшена
	@echo "$(YELLOW)Сборка Docker образов для продакшена...$(NC)"
	docker-compose -f $(COMPOSE_PROD_FILE) build

prod-up: ## Запустить в продакшене
	@echo "$(GREEN)Запуск в режиме продакшена...$(NC)"
	docker-compose -f $(COMPOSE_PROD_FILE) up -d
	@echo "$(GREEN)Продакшен запущен!$(NC)"

prod-down: ## Остановить продакшен
	@echo "$(RED)Остановка продакшена...$(NC)"
	docker-compose -f $(COMPOSE_PROD_FILE) down

prod-logs: ## Логи продакшена
	docker-compose -f $(COMPOSE_PROD_FILE) logs -f

# Утилиты
status: ## Показать статус всех контейнеров
	@echo "$(BLUE)Статус контейнеров:$(NC)"
	docker-compose -f $(COMPOSE_FILE) ps

health: ## Проверить здоровье сервисов
	@echo "$(BLUE)Проверка здоровья сервисов:$(NC)"
	@docker-compose -f $(COMPOSE_FILE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

clean: ## Очистить неиспользуемые образы и тома
	@echo "$(YELLOW)Очистка Docker...$(NC)"
	docker system prune -f
	docker volume prune -f

clean-all: ## Полная очистка (ОСТОРОЖНО!)
	@echo "$(RED)ВНИМАНИЕ: Полная очистка Docker!$(NC)"
	@read -p "Вы уверены? [y/N]: " confirm && [ "$$confirm" = "y" ]
	docker-compose -f $(COMPOSE_FILE) down -v
	docker system prune -af
	docker volume prune -af

# Разработка
dev-shell-admin: ## Войти в контейнер админ-панели
	docker-compose -f $(COMPOSE_FILE) exec admin-panel bash

dev-shell-bot: ## Войти в контейнер телеграм-бота
	docker-compose -f $(COMPOSE_FILE) exec telegram-bot bash

dev-shell-db: ## Войти в базу данных
	docker-compose -f $(COMPOSE_FILE) exec postgres psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

# Бэкапы
backup-db: ## Создать бэкап базы данных
	@echo "$(YELLOW)Создание бэкапа БД...$(NC)"
	docker-compose -f $(COMPOSE_FILE) exec -T postgres pg_dump -U $${POSTGRES_USER} $${POSTGRES_DB} > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)Бэкап создан!$(NC)"

# Быстрые команды
dev: build up ## Быстрый запуск для разработки
prod: prod-build prod-up ## Быстрый запуск для продакшена 