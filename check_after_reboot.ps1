# PowerShell скрипт проверки системы после перезагрузки

Write-Host "🔄 Проверка системы после перезагрузки..." -ForegroundColor Cyan

# 1. Проверяем статус всех контейнеров
Write-Host "`n📋 Статус контейнеров:" -ForegroundColor Yellow
docker-compose ps

# 2. Ждем полной инициализации
Write-Host "`n⏳ Ожидание инициализации (60 секунд)..." -ForegroundColor Yellow
Start-Sleep -Seconds 60

# 3. Проверяем логи телеграм бота
Write-Host "`n📝 Логи телеграм бота:" -ForegroundColor Yellow
docker logs rag_telegram_bot --tail 20

# 4. Проверяем импорты в Python
Write-Host "`n🐍 Проверка импортов Python:" -ForegroundColor Yellow
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
Write-Host "`n💚 Проверка здоровья системы:" -ForegroundColor Green
docker-compose ps | Select-String "healthy|Up"

Write-Host "`n✅ Проверка завершена!" -ForegroundColor Green 