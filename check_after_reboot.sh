#!/bin/bash
# Скрипт проверки системы после перезагрузки

echo "🔄 Проверка системы после перезагрузки..."

# 1. Проверяем статус всех контейнеров
echo "📋 Статус контейнеров:"
docker-compose ps

# 2. Ждем полной инициализации
echo "⏳ Ожидание инициализации (60 секунд)..."
sleep 60

# 3. Проверяем логи телеграм бота
echo "📝 Логи телеграм бота:"
docker logs rag_telegram_bot --tail 20

# 4. Проверяем импорты в Python
echo "🐍 Проверка импортов Python:"
docker exec rag_telegram_bot python -c "
try:
    from shared.utils.simple_rag import SimpleRAG
    print('✅ Импорт SimpleRAG успешен')
except Exception as e:
    print(f'❌ Ошибка импорта SimpleRAG: {e}')

try:
    from shared.utils.llm_client import SimpleLLMClient
    print('✅ Импорт SimpleLLMClient успешен')
except Exception as e:
    print(f'❌ Ошибка импорта SimpleLLMClient: {e}')

try:
    from bot.rag_service import RAGService
    print('✅ Импорт RAGService успешен')
except Exception as e:
    print(f'❌ Ошибка импорта RAGService: {e}')
"

# 5. Проверяем здоровье системы
echo "💚 Проверка здоровья системы:"
docker-compose ps | grep "healthy\|Up"

echo "✅ Проверка завершена!" 