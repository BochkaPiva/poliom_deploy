"""
Обработчики команд и сообщений для Telegram бота
"""

import logging
import sys
import re
from pathlib import Path
from typing import Dict, Any
import time
import asyncio
from datetime import timedelta

# Добавляем пути к модулям
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "shared"))
sys.path.insert(0, str(project_root / "services" / "telegram-bot"))

from aiogram import Dispatcher, types, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext

try:
    from bot.config import Config
    from bot.database import log_user_query, get_user_stats, check_database_health, get_documents_count, get_or_create_user, get_menu_sections, get_menu_items, get_menu_item_content, get_documents_by_ids, get_completed_documents, get_completed_documents_count, get_document_by_id
    from bot.rag_service import RAGService
except ImportError:
    # Fallback для тестирования
    import os
    import sys
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    from config import Config
    from database import log_user_query, get_user_stats, check_database_health, get_documents_count, get_or_create_user, get_menu_sections, get_menu_items, get_menu_item_content, get_documents_by_ids, get_completed_documents, get_completed_documents_count, get_document_by_id
    from rag_service import RAGService

logger = logging.getLogger(__name__)

# Инициализируем конфигурацию и RAG сервис
config = Config()
rag_service = RAGService(config.GIGACHAT_API_KEY)

# В начале файла добавляем временное хранилище для файлов
files_storage = {}

# Добавляем лимиты для безопасности
USER_FILE_LIMITS = {}  # {user_id: {'count': 0, 'last_reset': timestamp}}
MAX_FILES_PER_HOUR = 10  # Максимум файлов в час на пользователя

def check_user_file_limit(user_id: int) -> bool:
    """Проверка лимита скачивания файлов для пользователя"""
    current_time = time.time()
    
    if user_id not in USER_FILE_LIMITS:
        USER_FILE_LIMITS[user_id] = {'count': 0, 'last_reset': current_time}
    
    user_data = USER_FILE_LIMITS[user_id]
    
    # Сброс счетчика если прошел час
    if current_time - user_data['last_reset'] > 3600:  # 1 час
        user_data['count'] = 0
        user_data['last_reset'] = current_time
    
    # Проверяем лимит ДО увеличения счетчика
    if user_data['count'] >= MAX_FILES_PER_HOUR:
        return False
    
    # Увеличиваем счетчик только если лимит не превышен
    user_data['count'] += 1
    return True

def is_file_allowed_for_sharing(file_path: str, file_type: str) -> bool:
    """Проверка, можно ли отправлять данный тип файла"""
    # Проверяем, что file_path не пустой
    if not file_path or not file_type:
        return False
    
    # Разрешенные типы файлов
    allowed_types = ['pdf', 'docx', 'doc', 'txt', 'xlsx', 'xls']
    
    # Запрещенные паттерны в названии файла
    forbidden_patterns = [
        'конфиденциально',
        'секретно', 
        'персональные_данные',
        'зарплата_список',
        'password'
    ]
    
    file_path_lower = file_path.lower()
    
    # Проверяем тип файла
    if file_type.lower() not in allowed_types:
        return False
    
    # Проверяем запрещенные паттерны
    for pattern in forbidden_patterns:
        if pattern in file_path_lower:
            return False
    
    return True

async def log_file_download(user_id: int, file_path: str, file_title: str, success: bool):
    """Логирование скачивания файлов"""
    try:
        from datetime import datetime
        log_message = (
            f"FILE_DOWNLOAD: user_id={user_id}, "
            f"file='{file_title}', path='{file_path}', "
            f"success={success}, timestamp={datetime.now().isoformat()}"
        )
        logger.info(log_message)
        
        # Здесь можно добавить запись в отдельную таблицу логов файлов
        
    except Exception as e:
        logger.error(f"Ошибка логирования скачивания файла: {e}")

router = Router()

def cleanup_old_files():
    """Очистка старых файлов из хранилища (старше 1 часа)"""
    current_time = time.time()
    keys_to_remove = []
    
    for key, data in files_storage.items():
        if current_time - data.get('timestamp', 0) > 3600:  # 1 час
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del files_storage[key]
    
    if keys_to_remove:
        logger.info(f"Очищено {len(keys_to_remove)} устаревших записей файлов")

def is_blocked_response(response: str) -> bool:
    """Проверка, заблокирован ли ответ от GigaChat"""
    blocked_phrases = [
        "Генеративные языковые модели не обладают собственным мнением",
        "разговоры на чувствительные темы могут быть ограничены",
        "разговоры на некоторые темы временно ограничены",
        "Как и любая языковая модель, GigaChat не обладает собственным мнением",
        "К сожалению, иногда генеративные языковые модели могут создавать некорректные ответы",
        "ответы на вопросы, связанные с чувствительными темами, временно ограничены",
        "во избежание неправильного толкования, ответы на вопросы, связанные с чувствительными темами, временно ограничены"
    ]
    
    # Также проверяем на неполные ответы без конкретных дат для вопросов о зарплате
    if any(phrase in response for phrase in blocked_phrases):
        return True
    
    # Дополнительная проверка для ответов о зарплате без конкретных дат
    if ("заработная плата выплачивается два раза в месяц" in response.lower() and 
        "сроки выплаты" in response.lower() and 
        "устанавливаются в правилах" in response.lower() and
        not any(date in response for date in ['12', '27', '15'])):
        return True
    
    return False

def extract_key_information(chunks: list, question: str) -> str:
    """Извлечение ключевой информации из чанков когда GigaChat заблокирован"""
    if not chunks:
        return "Информация не найдена в корпоративной базе знаний."
    
    # Собираем релевантные фразы из чанков
    key_info = []
    question_words = set(question.lower().split())
    
    for chunk in chunks[:5]:  # Берем первые 5 наиболее релевантных чанков
        content = chunk.get('content', '')
        
        # Разбиваем на предложения
        sentences = content.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Пропускаем слишком короткие предложения
                continue
                
            # Проверяем, содержит ли предложение ключевые слова из вопроса
            sentence_words = set(sentence.lower().split())
            overlap = question_words & sentence_words
            
            if len(overlap) >= 1:  # Если есть пересечение слов
                key_info.append(sentence.strip())
                
        if len(key_info) >= 3:  # Ограничиваем количество предложений
            break
    
    if not key_info:
        return "По вашему вопросу найдены документы в корпоративной базе, но не удалось извлечь конкретную информацию. Рекомендую обратиться к HR-отделу для получения подробной консультации."
    
    # Формируем ответ
    result = "На основе корпоративных документов:\n\n"
    for i, info in enumerate(key_info, 1):
        result += f"{i}. {info}.\n"
    
    result += "\n💡 Для получения более подробной информации обратитесь к HR-отделу."
    
    # Проверяем, есть ли в вопросе ключевые слова о зарплате
    salary_keywords = ['зарплат', 'оплат', 'выплат', 'аванс', 'премии', 'вознаграждени']
    if any(keyword in question.lower() for keyword in salary_keywords):
        result += "\n💰 **Дополнительная информация о зарплате:**\n"
        result += "• Заработная плата выплачивается два раза в месяц: 12-го и 27-го числа\n"
        result += "• Размер первой выплаты (12-го числа) составляет 50% от оклада и постоянных выплат\n"
        result += "• Если дата выплаты приходится на выходной или праздничный день, выплата производится накануне\n"
        result += "• Заработная плата выплачивается в безналичной форме на банковский счет работника\n"
    
    return result

def extract_specific_data_patterns(context: str, question: str) -> str:
    """НЕ извлекает случайные данные - возвращает None для всех случаев"""
    # Убираем извлечение случайных данных полностью
    return None

def format_response_for_telegram(text: str) -> str:
    """Форматирование ответа для улучшения читаемости в Telegram"""
    if not text:
        return text
    
    # 1. Убираем LaTeX формулы и заменяем их на читаемый текст
    import re
    
    # Заменяем LaTeX формулы \[...\] на простой текст в рамках
    latex_pattern = r'\\\[(.*?)\\\]'
    def replace_latex(match):
        formula = match.group(1)
        # Очищаем от LaTeX команд
        clean_formula = formula.replace('\\text{', '').replace('}', '').replace('\\times', ' × ').replace('\\', '')
        return f"\n📋 `{clean_formula}`\n"
    
    text = re.sub(latex_pattern, replace_latex, text, flags=re.DOTALL)
    
    # 2. Исправляем нумерацию (убираем двойные точки)
    text = re.sub(r'(\d+)\.\.\s+', r'\1. ', text)
    
    # 3. Улучшаем форматирование заголовков
    text = re.sub(r'### (.+)', r'\n🔷 **\1**\n', text)
    text = re.sub(r'## (.+)', r'\n🔸 **\1**\n', text)
    
    # 4. Улучшаем форматирование списков
    # Заменяем длинные тире на обычные
    text = re.sub(r'^[-—–]\s+', '• ', text, flags=re.MULTILINE)
    
    # 5. Исправляем множественные переносы строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # 6. Убираем лишние пробелы в начале и конце строк
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    text = '\n'.join(cleaned_lines)
    
    # 7. Исправляем форматирование формул в тексте
    text = re.sub(r'([А-Яа-я\s]+)=([А-Яа-я\s\d×\(\)\-\+\/]+)', r'**\1** = `\2`', text)
    
    # 8. Улучшаем читаемость длинных формул
    if 'Размер премии' in text or 'базовое вознаграждение' in text:
        # Разбиваем длинные формулы на части
        text = text.replace(' × ', ' ×\n      ')
        text = text.replace('Суммарное базовое вознаграждение с учетом времени отсутствия на работе', 
                           'Суммарное базовое вознаграждение\n(с учетом времени отсутствия)')
    
    # 9. Добавляем разделители для лучшей читаемости
    # if '📚 **Источники:**' in text:
    #     text = text.replace('📚 **Источники:**', '\n' + '─' * 30 + '\n📚 **Источники:**')
    
    # Убираем лишние пробелы и переносы строк - УДАЛЕНО
    # text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    return text.strip()

def create_faq_keyboard():
    """Создание клавиатуры для FAQ на основе данных из БД"""
    try:
        sections = get_menu_sections()
        keyboard_buttons = []
        
        for section in sections:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=section['title'], 
                    callback_data=f"faq_section_{section['id']}"
                )
            ])
        
        keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        return keyboard
    except Exception as e:
        logger.error(f"Ошибка создания FAQ клавиатуры: {e}")
        # Fallback клавиатура
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ошибка загрузки FAQ", callback_data="back_to_main")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        return keyboard

def create_main_keyboard(user_telegram_id: int = None):
    """Создание основной клавиатуры"""
    keyboard_buttons = [
        [InlineKeyboardButton(text="📚 FAQ", callback_data="show_faq")],
        [InlineKeyboardButton(text="🔍 Умный поиск", callback_data="smart_search")],
        [InlineKeyboardButton(text="📄 Документы", callback_data="show_documents")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")]
    ]
    
    # Добавляем кнопку статуса системы только для администратора
    if user_telegram_id == 1463020624:
        keyboard_buttons.append([InlineKeyboardButton(text="🏥 Статус системы", callback_data="show_health")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return keyboard

def create_section_keyboard(section_id: int):
    """Создание клавиатуры для вопросов в разделе"""
    try:
        items = get_menu_items(section_id)
        keyboard_buttons = []
        
        for item in items:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=item['title'], 
                    callback_data=f"faq_item_{item['id']}"
                )
            ])
        
        keyboard_buttons.append([InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        return keyboard
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры раздела {section_id}: {e}")
        # Fallback клавиатура
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ошибка загрузки вопросов", callback_data="show_faq")],
            [InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")]
        ])
        return keyboard

def create_documents_keyboard(page: int = 0, documents_per_page: int = 10):
    """Создание клавиатуры для списка документов с пагинацией"""
    try:
        # Получаем общее количество документов
        total_documents = get_completed_documents_count()
        
        # Вычисляем пагинацию
        total_pages = (total_documents + documents_per_page - 1) // documents_per_page
        offset = page * documents_per_page
        
        # Получаем документы для текущей страницы
        documents = get_completed_documents(limit=documents_per_page, offset=offset)
        
        keyboard_buttons = []
        
        # Добавляем кнопки документов
        for doc in documents:
            title = doc.get('title') or doc.get('original_filename', 'Документ')
            # Ограничиваем длину названия для кнопки
            display_title = title[:35] + "..." if len(title) > 35 else title
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📄 {display_title}", 
                    callback_data=f"doc_info_{doc['id']}"
                )
            ])
        
        # Добавляем навигацию если есть больше одной страницы
        if total_pages > 1:
            nav_buttons = []
            
            # Кнопка "Предыдущая"
            if page > 0:
                nav_buttons.append(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data=f"docs_page_{page-1}")
                )
            
            # Информация о текущей странице
            nav_buttons.append(
                InlineKeyboardButton(
                    text=f"{page + 1}/{total_pages}", 
                    callback_data="current_page"
                )
            )
            
            # Кнопка "Следующая"
            if page < total_pages - 1:
                nav_buttons.append(
                    InlineKeyboardButton(text="Вперед ➡️", callback_data=f"docs_page_{page+1}")
                )
            
            keyboard_buttons.append(nav_buttons)
        
        # Кнопка возврата
        keyboard_buttons.append([
            InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard_buttons), total_documents
        
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры документов: {e}")
        # Fallback клавиатура
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Ошибка загрузки документов", callback_data="back_to_main")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ])
        return keyboard, 0

def get_document_info(doc_id: int):
    """Получение информации о документе"""
    return get_document_by_id(doc_id)

async def get_or_create_user_async(telegram_id: int, username: str = None, 
                                 first_name: str = None, last_name: str = None):
    """Асинхронная версия get_or_create_user"""
    loop = asyncio.get_event_loop()
    
    return await loop.run_in_executor(
        None, 
        get_or_create_user, 
        telegram_id, 
        username, 
        first_name,
        last_name
    )

async def log_user_query_async(user_id: int, query: str, response: str, 
                              response_time: float = None, similarity_score: float = None,
                              documents_used: str = None):
    """Асинхронная версия log_user_query"""
    loop = asyncio.get_event_loop()
    
    return await loop.run_in_executor(
        None,
        log_user_query,
        user_id,
        query,
        response,
        response_time,
        similarity_score,
        documents_used
    )

@router.message(CommandStart())
async def start_handler(message: Message):
    """Обработчик команды /start"""
    try:
        # Получаем или создаем пользователя
        user = await get_or_create_user_async(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        if not user.is_active:
            await message.answer(
                "❌ Ваш аккаунт заблокирован. Обратитесь к администратору."
            )
            return
        
        welcome_text = f"""👋 Привет, {message.from_user.first_name or 'пользователь'}!

🤖 **POLIOM HR Assistant** - ваш помощник по вопросам трудовых отношений.

**Что я умею:**
📚 **FAQ** - ответы на частые вопросы
🔍 **Умный поиск** - поиск по документам компании
📋 **Точные ответы** - с указанием источников

**Быстрый старт:**
• Просто задайте мне вопрос своими словами
• Я найду релевантную информацию в базе знаний
• Получите ответ с указанием источников

Для получения справки используйте команду /help"""
        
        await message.answer(welcome_text.strip(), reply_markup=create_main_keyboard(message.from_user.id), parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в start_handler: {e}")
        await message.answer("Произошла ошибка. Попробуйте позже.")

@router.message(Command("help"))
async def help_handler(message: Message):
    """Обработчик команды /help"""
    help_text = """📖 **Справка по использованию бота:**

**Команды:**
• /start - Начать работу с ботом
• /help - Показать эту справку
• /stats - Ваша статистика

**Как пользоваться:**
• Просто напишите свой вопрос
• Бот найдет релевантную информацию в документах
• Получите ответ с указанием источников

**Примеры вопросов:**
• "Как оформить отпуск?"
• "Какие документы нужны для командировки?"
• "Процедура увольнения"
• "Размер компенсации за переработку"

🤖 Я использую искусственный интеллект для поиска ответов в корпоративной базе знаний."""
    
    await message.answer(help_text.strip(), parse_mode='Markdown')

@router.message(Command("stats"))
async def stats_handler(message: Message):
    """Обработчик команды /stats"""
    try:
        # Получаем пользователя
        user = await get_or_create_user_async(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        # Получаем статистику
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            None,
            get_user_stats,
            message.from_user.id
        )
        
        if 'error' in stats:
            await message.answer("❌ Ошибка получения статистики")
            return
        
        # Конвертируем время в часовой пояс Омска (+6 UTC)
        omsk_offset = timedelta(hours=6)
        
        created_at_omsk = None
        if stats['created_at']:
            created_at_omsk = stats['created_at'] + omsk_offset
            
        last_query_at_omsk = None
        if stats['last_query_at']:
            last_query_at_omsk = stats['last_query_at'] + omsk_offset
        
        stats_text = f"""📊 **Ваша статистика:**

👤 **Пользователь:** {(stats['first_name'] or '') + (' ' + stats['last_name'] if stats['last_name'] else '') or stats['username'] or 'Неизвестно'}
🆔 **ID:** {stats['telegram_id']}
📅 **Регистрация:** {created_at_omsk.strftime('%d.%m.%Y %H:%M') + ' (Омск)' if created_at_omsk else 'Неизвестно'}
📝 **Запросов:** {stats['query_count']}
🕐 **Последний запрос:** {last_query_at_omsk.strftime('%d.%m.%Y %H:%M') + ' (Омск)' if last_query_at_omsk else 'Нет запросов'}
✅ **Статус:** {'Активен' if stats['is_active'] else 'Заблокирован'}"""
        
        await message.answer(stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в stats_handler: {e}")
        await message.answer("❌ Произошла ошибка при получении статистики")

@router.message(Command("health"))
async def health_handler(message: Message):
    """Обработчик команды /health"""
    try:
        health_status = []
        
        # Проверяем базу данных
        try:
            loop = asyncio.get_event_loop()
            db_health = await loop.run_in_executor(None, check_database_health)
            if db_health:
                health_status.append("✅ База данных: OK")
            else:
                health_status.append("❌ База данных: Ошибка")
        except Exception as e:
            health_status.append(f"❌ База данных: {str(e)[:50]}")
        
        # Проверяем RAG сервис
        try:
            rag_health = await rag_service.health_check()
            if rag_health.get('overall', False):
                health_status.append("✅ RAG сервис: OK")
            else:
                health_status.append("❌ RAG сервис: Ошибка")
        except Exception as e:
            health_status.append(f"❌ RAG сервис: {str(e)[:50]}")
        
        # Проверяем количество документов
        try:
            loop = asyncio.get_event_loop()
            docs_count = await loop.run_in_executor(None, get_documents_count)
            health_status.append(f"📄 Документов в базе: {docs_count}")
        except Exception as e:
            health_status.append(f"❌ Документы: {str(e)[:50]}")
        
        # Формируем ответ
        health_message = "🏥 **Статус системы:**\n\n" + "\n".join(health_status)
        
        await message.answer(health_message)
        
    except Exception as e:
        logger.error(f"Ошибка в health_handler: {e}")
        await message.answer("❌ Произошла ошибка при проверке статуса системы")

@router.message(F.text)
async def question_handler(message: Message):
    """Обработчик текстовых сообщений (вопросов пользователей)"""
    try:
        # Получаем или создаем пользователя
        user = await get_or_create_user_async(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        # Проверяем, не заблокирован ли пользователь
        if not user.is_active:
            await message.answer("❌ Ваш доступ к боту ограничен. Обратитесь к администратору.")
            return
        
        # Отправляем временное сообщение о поиске
        search_message = await message.answer("🔍 **Ищу ответ на ваш вопрос...**", parse_mode='Markdown')
        
        # Отправляем индикатор "печатает"
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Получаем ответ от RAG системы
        result = await rag_service.answer_question(message.text, user_id=user.id)
        
        # Проверяем качество результата
        if not result or 'answer' not in result:
            response_text = "❌ Извините, не удалось обработать ваш запрос. Попробуйте переформулировать вопрос."
        else:
            # Логируем полученные данные для отладки
            chunks = result.get('chunks', [])
            logger.info(f"Получено {len(chunks)} чанков от RAG системы")
            
            # Проверяем релевантность найденных чанков
            relevant_chunks = []
            
            if chunks:
                # Фильтруем чанки по схожести с более мягкими порогами
                for i, chunk in enumerate(chunks):
                    similarity = chunk.get('similarity', 0)
                    logger.info(f"Чанк {i+1}: similarity={similarity}")
                    
                    if similarity >= 0.3:  # Повышен порог с 0.25 для оптимизации
                        relevant_chunks.append(chunk)
                        logger.info(f"Чанк {i+1} добавлен как релевантный (similarity={similarity})")
                    else:
                        # Проверяем, содержит ли чанк ключевые слова из вопроса
                        question_words = set(message.text.lower().split())
                        chunk_words = set(chunk.get('content', '').lower().split())
                        
                        # Если есть пересечение ключевых слов, добавляем чанк
                        overlap = question_words & chunk_words
                        if len(overlap) >= 1:
                            relevant_chunks.append(chunk)
                            logger.info(f"Чанк {i+1} добавлен по ключевым словам: {overlap}")
            
            # Логируем итоговое количество релевантных чанков
            logger.info(f"Итого релевантных чанков: {len(relevant_chunks)}")
            logger.info(f"Ответ GigaChat заблокирован: {is_blocked_response(result['answer'])}")
            
            # Упрощенная логика обработки ответов
            if len(relevant_chunks) > 0:
                if is_blocked_response(result['answer']):
                    logger.info("GigaChat заблокирован, извлекаем информацию из контекста")
                    response_text = extract_key_information(relevant_chunks, message.text)
                else:
                    logger.info("Используем ответ GigaChat")
                    response_text = result['answer']
                    
                    # Добавляем источники с дедупликацией
                    if result.get('sources'):
                        # Дедуплицируем источники по названию
                        unique_sources = {}
                        for source in result['sources']:
                            title = source.get('title', 'Документ')
                            # Убираем фильтр по длине - все названия допустимы
                            if title and title not in unique_sources:
                                unique_sources[title] = source
                        
                        if unique_sources:
                            # response_text += "\n\n" + "─" * 30
                            response_text += "\n\n💡 Если ответ не удовлетворил запросу, попробуйте переформулировать его, либо воспользуйтесь источниками для самостоятельного поиска."
                            response_text += "\n\n📚 **Источники:**"
                            for i, title in enumerate(unique_sources.keys(), 1):
                                response_text += f"\n{i}. {title}"
                            
                            # Дедуплицируем файлы по названию, но сохраняем полную информацию включая file_path
                            unique_files = {}
                            for file_info in result.get('files', []):
                                title = file_info.get('title', 'Документ')
                                # Убираем фильтр по длине и для файлов
                                if title and title not in unique_files:
                                    unique_files[title] = file_info
                            
                            # Обновляем файлы дедуплицированными, сохраняя file_path
                            result['files'] = list(unique_files.values())
            else:
                logger.info("Нет релевантных чанков - возвращаем fallback ответ")
                if result.get('answer') and not is_blocked_response(result['answer']):
                    response_text = result['answer']
                else:
                    response_text = (
                        "🔍 **Информация не найдена**\n\n"
                        "К сожалению, по вашему вопросу не найдено релевантной информации в корпоративной базе знаний.\n\n"
                        "**Рекомендации:**\n"
                        "• Попробуйте переформулировать вопрос\n"
                        "• Используйте другие ключевые слова\n"
                        "• Обратитесь к HR-отделу для получения консультации\n\n"
                        "📞 **Контакты HR-отдела:** [укажите контакты]"
                    )
        
        # Применяем форматирование для улучшения читаемости
        if response_text:
            response_text = format_response_for_telegram(response_text)
        
        # Отправляем ответ
        try:
            # Создаем клавиатуру с дополнительными кнопками
            keyboard_buttons = []
            
            # Если есть файлы-источники, добавляем кнопку для их показа
            files = result.get('files', []) if result else []
            if files:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"📎 Файлы-источники ({len(files)})", 
                        callback_data=f"show_files_{message.message_id}"
                    )
                ])
            
            # Добавляем кнопку "Назад"
            keyboard_buttons.append([
                InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")
            ])
            
            back_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            # Сохраняем информацию о файлах для последующего использования
            if files:
                # Очищаем старые файлы перед добавлением новых
                cleanup_old_files()
                
                # Детальное логирование для отладки
                logger.info(f"Получено файлов от RAG системы: {len(files)}")
                for i, file_info in enumerate(files):
                    logger.info(f"Файл {i+1}: title='{file_info.get('title', 'НЕТ_НАЗВАНИЯ')}', "
                              f"file_path='{file_info.get('file_path', 'ПУСТОЙ_ПУТЬ')}', "
                              f"document_id={file_info.get('document_id', 'НЕТ_ID')}, "
                              f"similarity={file_info.get('similarity', 'НЕТ_SIMILARITY')}")
                
                # Сохраняем файлы в временное хранилище с временной меткой
                files_storage[str(message.message_id)] = {
                    'files': files,
                    'timestamp': time.time()
                }
                logger.info(f"Сохранены файлы для сообщения {message.message_id}: {[f['title'] for f in files]}")
            
            # Пытаемся отправить с разными форматами markdown
            try:
                await search_message.edit_text(response_text, reply_markup=back_keyboard, parse_mode='Markdown')
            except:
                try:
                    # Убираем все markdown форматирование
                    clean_text = response_text.replace('**', '').replace('*', '').replace('_', '').replace('`', '')
                    await search_message.edit_text(clean_text, reply_markup=back_keyboard)
                except:
                    await search_message.edit_text("Ответ получен, но возникла ошибка форматирования.", reply_markup=back_keyboard)
        
        except Exception as send_error:
            logger.error(f"Ошибка отправки сообщения: {send_error}")
            # Fallback - отправляем простое сообщение
            try:
                simple_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                ])
                await message.answer("Ответ готов, но возникла техническая ошибка при отправке.", reply_markup=simple_keyboard)
            except:
                await message.answer("Техническая ошибка. Попробуйте переформулировать вопрос.")
        
    except Exception as e:
        logger.error(f"Ошибка в question_handler: {e}")
        try:
            await message.answer(
                "❌ Произошла ошибка при обработке вашего запроса. Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                ])
            )
        except:
            await message.answer("❌ Техническая ошибка.")

@router.callback_query(F.data == "show_faq")
async def show_faq_callback(callback: CallbackQuery):
    """Показать FAQ меню"""
    await callback.message.edit_text(
        "📚 **Часто задаваемые вопросы**\n\nВыберите интересующую вас категорию:",
        reply_markup=create_faq_keyboard(),
        parse_mode='Markdown'
    )
    await callback.answer()

@router.callback_query(F.data == "show_stats")
async def show_stats_callback(callback: CallbackQuery):
    """Показать статистику через callback"""
    try:
        # Получаем пользователя
        user = await get_or_create_user_async(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name
        )
        
        # Получаем статистику
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(
            None,
            get_user_stats,
            callback.from_user.id
        )
        
        if 'error' in stats:
            await callback.message.edit_text("❌ Ошибка получения статистики")
            return
        
        # Конвертируем время в часовой пояс Омска (+6 UTC)
        omsk_offset = timedelta(hours=6)
        
        created_at_omsk = None
        if stats['created_at']:
            created_at_omsk = stats['created_at'] + omsk_offset
            
        last_query_at_omsk = None
        if stats['last_query_at']:
            last_query_at_omsk = stats['last_query_at'] + omsk_offset
        
        stats_text = f"""📊 **Ваша статистика:**

👤 **Пользователь:** {(stats['first_name'] or '') + (' ' + stats['last_name'] if stats['last_name'] else '') or stats['username'] or 'Неизвестно'}
🆔 **ID:** {stats['telegram_id']}
📅 **Регистрация:** {created_at_omsk.strftime('%d.%m.%Y %H:%M') + ' (Омск)' if created_at_omsk else 'Неизвестно'}
📝 **Запросов:** {stats['query_count']}
🕐 **Последний запрос:** {last_query_at_omsk.strftime('%d.%m.%Y %H:%M') + ' (Омск)' if last_query_at_omsk else 'Нет запросов'}
✅ **Статус:** {'Активен' if stats['is_active'] else 'Заблокирован'}"""
        
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(stats_text, reply_markup=back_keyboard, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в show_stats_callback: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при получении статистики")
    
    await callback.answer()

@router.callback_query(F.data == "show_health")
async def show_health_callback(callback: CallbackQuery):
    """Показать статус системы через callback"""
    try:
        health_status = []
        
        # Проверяем базу данных
        try:
            loop = asyncio.get_event_loop()
            db_health = await loop.run_in_executor(None, check_database_health)
            if db_health:
                health_status.append("✅ База данных: OK")
            else:
                health_status.append("❌ База данных: Ошибка")
        except Exception as e:
            health_status.append(f"❌ База данных: {str(e)[:50]}")
        
        # Проверяем RAG сервис
        try:
            rag_health = await rag_service.health_check()
            if rag_health.get('overall', False):
                health_status.append("✅ RAG сервис: OK")
            else:
                health_status.append("❌ RAG сервис: Ошибка")
        except Exception as e:
            health_status.append(f"❌ RAG сервис: {str(e)[:50]}")
        
        # Проверяем количество документов
        try:
            loop = asyncio.get_event_loop()
            docs_count = await loop.run_in_executor(None, get_documents_count)
            health_status.append(f"📄 Документов в базе: {docs_count}")
        except Exception as e:
            health_status.append(f"❌ Документы: {str(e)[:50]}")
        
        # Формируем ответ
        health_message = "🏥 **Статус системы:**\n\n" + "\n".join(health_status)
        
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(health_message, reply_markup=back_keyboard, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в show_health_callback: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при проверке статуса системы")
    
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    """Вернуться в главное меню"""
    welcome_text = f"""👋 Привет, {callback.from_user.first_name or 'пользователь'}!

🤖 **POLIOM HR Assistant** - ваш помощник по вопросам трудовых отношений.

**Что я умею:**
📚 **FAQ** - ответы на частые вопросы
🔍 **Умный поиск** - поиск по документам компании
📋 **Точные ответы** - с указанием источников

**Быстрый старт:**
• Просто задайте мне вопрос своими словами
• Я найду релевантную информацию в базе знаний
• Получите ответ с указанием источников

Для получения справки используйте команду /help"""
    
    await callback.message.edit_text(welcome_text.strip(), reply_markup=create_main_keyboard(callback.from_user.id), parse_mode='Markdown')
    await callback.answer()

@router.callback_query(F.data.startswith("faq_section_"))
async def faq_section_callback(callback: CallbackQuery):
    """Обработчик выбора раздела FAQ"""
    try:
        section_id = int(callback.data.replace("faq_section_", ""))
        
        # Получаем информацию о разделе
        sections = get_menu_sections()
        section = next((s for s in sections if s['id'] == section_id), None)
        
        if not section:
            await callback.message.edit_text(
                "❌ Раздел не найден",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")]
                ])
            )
            await callback.answer()
            return
        
        # Создаем клавиатуру с вопросами
        keyboard = create_section_keyboard(section_id)
        
        section_text = f"📚 **{section['title']}**\n\nВыберите интересующий вас вопрос:"
        
        await callback.message.edit_text(
            section_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в faq_section_callback: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при загрузке раздела",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")]
            ])
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("faq_item_"))
async def faq_item_callback(callback: CallbackQuery):
    """Обработчик выбора конкретного вопроса FAQ"""
    try:
        item_id = int(callback.data.replace("faq_item_", ""))
        
        # Получаем содержимое элемента меню
        item_data = get_menu_item_content(item_id)
        
        if not item_data:
            await callback.message.edit_text(
                "❌ Вопрос не найден",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")]
                ])
            )
            await callback.answer()
            return
        
        # Формируем ответ с источником
        answer_text = f"❓ **{item_data['title']}**\n\n{item_data['content']}"
        
        # Добавляем информацию об источниках только если они есть
        source_names = item_data.get('source_document_names', [])
        source_document_ids = item_data.get('source_document_ids', [])
        
        if source_names and source_document_ids:
            answer_text += "\n\n📚 **Источники:**"
            for i, (source_name, doc_id) in enumerate(zip(source_names, source_document_ids), 1):
                answer_text += f"\n{i}. {source_name}"         
        # Создаем простую клавиатуру для возврата
        keyboard_buttons = [
            [InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ]
        
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            answer_text,
            reply_markup=back_keyboard,
            parse_mode='Markdown'
        )
        
        # Логируем просмотр FAQ
        user = await get_or_create_user_async(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name
        )
        
        # Формируем строку с источниками для логирования
        sources_str = ", ".join(source_names) if source_names else "FAQ Database"
        
        await log_user_query_async(
            user_id=user.id,
            query=f"FAQ: {item_data['title']}",
            response=item_data['content'],
            documents_used=sources_str
        )
            
    except Exception as e:
        logger.error(f"Ошибка в faq_item_callback: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при загрузке ответа",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К разделам", callback_data="show_faq")]
            ])
        )
    
    await callback.answer()

@router.callback_query(F.data == "smart_search")
async def smart_search_callback(callback: CallbackQuery):
    """Обработчик кнопки умного поиска"""
    await callback.message.edit_text(
        "🔍 **Умный поиск**\n\nПросто напишите свой вопрос, и я найду ответ в корпоративной базе знаний.\n\n**Примеры вопросов:**\n• Как оформить отпуск?\n• Какие документы нужны для командировки?\n• Размер компенсации за переработку\n\nНапишите ваш вопрос:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
        ]),
        parse_mode='Markdown'
    )
    await callback.answer()

@router.callback_query(F.data.startswith("faq_"))
async def old_faq_callback(callback: CallbackQuery):
    """Обработчик старых FAQ callback (для совместимости)"""
    # Перенаправляем на новое FAQ меню
    await show_faq_callback(callback)

@router.callback_query(F.data.startswith("show_files_"))
async def show_files_callback(callback: CallbackQuery):
    """
    Обработчик кнопки "Файлы-источники" - теперь отправляет файлы напрямую пользователю
    с проверками безопасности и лимитами
    """
    try:
        message_id = callback.data.split("_")[-1]
        
        # Проверяем лимит пользователя
        if not check_user_file_limit(callback.from_user.id):
            # Создаем клавиатуру для возврата при превышении лимита
            limit_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Задать новый вопрос", callback_data="smart_search")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
            
            await callback.message.answer(
                "⏰ **Превышен лимит скачивания файлов**\n\n"
                f"Максимум {MAX_FILES_PER_HOUR} файлов в час. "
                "Попробуйте позже.",
                reply_markup=limit_keyboard,
                parse_mode='Markdown'
            )
            await callback.answer()
            return
        
        # Правильно извлекаем файлы из storage
        storage_data = files_storage.get(message_id, {})
        files = storage_data.get('files', []) if isinstance(storage_data, dict) else []
        
        if not files:
            # Создаем клавиатуру для возврата когда файлы недоступны
            no_files_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Задать новый вопрос", callback_data="smart_search")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
            ])
            
            await callback.message.answer(
                "📁 **Файлы недоступны**\n\n"
                "Файлы для этого ответа больше не доступны. "
                "Возможно, истекло время хранения.",
                reply_markup=no_files_keyboard,
                parse_mode='Markdown'
            )
            await callback.answer()
            return
        
        # Отправляем информацию о файлах
        files_info = "📎 **Файлы-источники для вашего запроса:**\n\n"
        for i, file_info in enumerate(files, 1):
            title = file_info.get('title', 'Без названия')
            similarity = file_info.get('similarity', 0)
            # Конвертируем similarity в проценты если это десятичная дробь
            relevance = int(similarity * 100) if similarity <= 1.0 else int(similarity)
            files_info += f"{i}. **{title}** (релевантность: {relevance}%)\n"
        
        files_info += f"\n📤 Отправляю {len(files)} файл(ов)...\n"
        await callback.message.answer(files_info, parse_mode='Markdown')
        
        # Отправляем файлы
        sent_count = 0
        failed_count = 0
        
        for i, file_info in enumerate(files, 1):
            try:
                title = file_info.get('title', 'Без названия')
                file_path = file_info.get('file_path', '')
                file_type = file_info.get('file_type', '')
                original_filename = file_info.get('original_filename', 'document')
                
                if not file_path:
                    await callback.message.answer(f"❌ {i}. **{title}**\nПуть к файлу не указан")
                    await log_file_download(callback.from_user.id, '', title, False)
                    failed_count += 1
                    continue
                
                # Проверяем, разрешен ли файл для отправки
                if not is_file_allowed_for_sharing(file_path, file_type):
                    await callback.message.answer(
                        f"🔒 {i}. **{title}**\n"
                        "Файл недоступен для отправки по соображениям безопасности"
                    )
                    await log_file_download(callback.from_user.id, file_path, title, False)
                    failed_count += 1
                    continue
                
                # Проверяем существование файла
                file_path_obj = Path(file_path)
                if not file_path_obj.exists():
                    await callback.message.answer(f"❌ {i}. **{title}**\nФайл не найден на диске: {file_path_obj.name}")
                    await log_file_download(callback.from_user.id, file_path, title, False)
                    failed_count += 1
                    continue
                
                # Проверяем размер файла (Telegram лимит 50MB)
                file_size = file_path_obj.stat().st_size
                if file_size > 50 * 1024 * 1024:  # 50MB в байтах
                    size_mb = file_size / (1024 * 1024)
                    await callback.message.answer(
                        f"📊 {i}. **{title}**\n"
                        f"Файл слишком большой для отправки ({size_mb:.1f} MB > 50 MB)\n"
                        f"📁 Файл: `{file_path_obj.name}`"
                    )
                    await log_file_download(callback.from_user.id, file_path, title, False)
                    failed_count += 1
                    continue
                
                # Отправляем файл
                try:
                    # Определяем имя файла для отправки
                    send_filename = original_filename if original_filename else file_path_obj.name
                    if not send_filename.lower().endswith(f'.{file_type.lower()}'):
                        send_filename += f'.{file_type.lower()}'
                    
                    file_input = FSInputFile(
                        path=str(file_path_obj),
                        filename=send_filename
                    )
                    
                    similarity = file_info.get('similarity', 0)
                    # Конвертируем similarity в проценты если это десятичная дробь
                    relevance = int(similarity * 100) if similarity <= 1.0 else int(similarity)
                    caption = f"📄 **{title}**\n📊 Релевантность: {relevance}%"
                    
                    await callback.message.answer_document(
                        document=file_input,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"Файл успешно отправлен пользователю {callback.from_user.id}: {title}")
                    await log_file_download(callback.from_user.id, file_path, title, True)
                    sent_count += 1
                    
                    # Небольшая задержка между отправками
                    await asyncio.sleep(0.5)
                    
                except Exception as send_error:
                    logger.error(f"Ошибка отправки файла {title}: {send_error}")
                    await callback.message.answer(f"❌ {i}. **{title}**\nОшибка при отправке файла")
                    await log_file_download(callback.from_user.id, file_path, title, False)
                    failed_count += 1
                    
            except Exception as file_error:
                logger.error(f"Ошибка обработки файла {i}: {file_error}")
                await callback.message.answer(f"❌ {i}. Ошибка обработки файла")
                failed_count += 1
        
        # Создаем клавиатуру для навигации после отправки файлов
        navigation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Задать новый вопрос", callback_data="smart_search")],
            [InlineKeyboardButton(text="📚 FAQ", callback_data="show_faq"),
             InlineKeyboardButton(text="📊 Статистика", callback_data="show_stats")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        
        # Итоговое сообщение с клавиатурой
        if sent_count > 0:
            summary = f"✅ **Отправлено файлов: {sent_count}**"
            if failed_count > 0:
                summary += f"\n❌ Не удалось отправить: {failed_count}"
            summary += "\n\n💡 **Что дальше?**\nВыберите действие из меню ниже:"
        else:
            summary = "❌ **Не удалось отправить ни одного файла**"
            if failed_count > 0:
                summary += f"\nОшибок: {failed_count}"
            summary += "\n\n🔄 **Попробуйте:**\n• Задать вопрос по-другому\n• Обратиться к FAQ\n• Связаться с HR-отделом"
        
        await callback.message.answer(
            summary, 
            reply_markup=navigation_keyboard,
            parse_mode='Markdown'
        )
        
        # Очищаем файлы из хранилища после отправки
        if message_id in files_storage:
            del files_storage[message_id]
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в show_files_callback: {e}")
        
        # Создаем клавиатуру для навигации при ошибке
        error_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Задать новый вопрос", callback_data="smart_search")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        
        await callback.message.answer(
            "❌ **Произошла ошибка при обработке файлов**\n\n"
            "Попробуйте задать вопрос заново или воспользуйтесь другими функциями бота.",
            reply_markup=error_keyboard,
            parse_mode='Markdown'
        )
        await callback.answer()

@router.callback_query(F.data == "show_documents")
async def show_documents_callback(callback: CallbackQuery):
    """Показать список документов"""
    try:
        keyboard, total_docs = create_documents_keyboard(page=0)
        
        if total_docs == 0:
            await callback.message.edit_text(
                "📄 **Документы**\n\n❌ В базе данных нет доступных документов.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
                ]),
                parse_mode='Markdown'
            )
        else:
            await callback.message.edit_text(
                f"📄 **Корпоративные документы**\n\nВсего документов: {total_docs}\n\nВыберите документ для просмотра:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка в show_documents_callback: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при загрузке документов",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")]
            ])
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("docs_page_"))
async def docs_page_callback(callback: CallbackQuery):
    """Обработчик пагинации документов"""
    try:
        page = int(callback.data.replace("docs_page_", ""))
        keyboard, total_docs = create_documents_keyboard(page=page)
        
        await callback.message.edit_text(
            f"📄 **Корпоративные документы**\n\nВсего документов: {total_docs}\n\nВыберите документ для просмотра:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка в docs_page_callback: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при навигации",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Документы", callback_data="show_documents")]
            ])
        )
    
    await callback.answer()

def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown"""
    if not text:
        return text
    
    # Экранируем специальные символы Markdown
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

@router.callback_query(F.data.startswith("doc_info_"))
async def doc_info_callback(callback: CallbackQuery):
    """Показать информацию о документе"""
    try:
        doc_id = int(callback.data.replace("doc_info_", ""))
        doc_info = get_document_info(doc_id)
        
        if not doc_info:
            await callback.message.edit_text(
                "❌ Документ не найден",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ])
            )
            await callback.answer()
            return
        
        # Форматируем размер файла
        file_size = doc_info.get('file_size', 0)
        if file_size:
            if file_size < 1024:
                size_str = f"{file_size} байт"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} КБ"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} МБ"
        else:
            size_str = "Неизвестно"
        
        # Форматируем дату создания
        created_at = doc_info.get('created_at')
        if created_at:
            # Конвертируем в часовой пояс Омска (+6 UTC)
            from datetime import timedelta
            omsk_offset = timedelta(hours=6)
            created_at_omsk = created_at + omsk_offset
            date_str = created_at_omsk.strftime('%d.%m.%Y %H:%M (Омск)')
        else:
            date_str = "Неизвестно"
        
        # Экранируем специальные символы в названиях
        title_escaped = escape_markdown(doc_info['title'])
        filename_escaped = escape_markdown(doc_info['original_filename'])

        info_text = f"""📄 **{title_escaped}**

📁 **Имя файла:** {filename_escaped}
📊 **Размер:** {size_str}
🗂 **Тип:** {doc_info.get('file_type', 'Неизвестно').upper()}
📅 **Добавлен:** {date_str}
✅ **Статус:** Обработан и доступен"""
        
        # Создаем клавиатуру с возможностью скачивания
        keyboard_buttons = []
        
        # Проверяем, можно ли скачать файл
        file_path = doc_info.get('file_path', '')
        file_type = doc_info.get('file_type', '')
        
        if file_path and is_file_allowed_for_sharing(file_path, file_type):
            keyboard_buttons.append([
                InlineKeyboardButton(text="📥 Скачать документ", callback_data=f"download_doc_{doc_id}")
            ])
        
        keyboard_buttons.extend([
            [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            info_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка в doc_info_callback: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при загрузке информации о документе",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
            ])
        )
    
    await callback.answer()

@router.callback_query(F.data.startswith("download_doc_"))
async def download_doc_callback(callback: CallbackQuery):
    """Скачать документ"""
    try:
        doc_id = int(callback.data.replace("download_doc_", ""))
        
        # Проверяем лимит пользователя
        if not check_user_file_limit(callback.from_user.id):
            await callback.message.answer(
                "⏰ **Превышен лимит скачивания файлов**\n\n"
                f"Максимум {MAX_FILES_PER_HOUR} файлов в час. "
                "Попробуйте позже.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ]),
                parse_mode='Markdown'
            )
            await callback.answer()
            return
        
        doc_info = get_document_info(doc_id)
        
        if not doc_info:
            await callback.message.answer(
                "❌ Документ не найден",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ])
            )
            await callback.answer()
            return
        
        file_path = doc_info.get('file_path', '')
        file_type = doc_info.get('file_type', '')
        title = doc_info.get('title', 'Документ')
        
        if not file_path:
            await callback.message.answer(
                f"❌ **{title}**\nПуть к файлу не указан",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ])
            )
            await log_file_download(callback.from_user.id, '', title, False)
            await callback.answer()
            return
        
        # Проверяем, разрешен ли файл для отправки
        if not is_file_allowed_for_sharing(file_path, file_type):
            await callback.message.answer(
                f"🔒 **{title}**\n"
                "Файл недоступен для отправки по соображениям безопасности",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ])
            )
            await log_file_download(callback.from_user.id, file_path, title, False)
            await callback.answer()
            return
        
        # Проверяем существование файла
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            await callback.message.answer(
                f"❌ **{title}**\nФайл не найден на диске: {file_path_obj.name}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ])
            )
            await log_file_download(callback.from_user.id, file_path, title, False)
            await callback.answer()
            return
        
        # Проверяем размер файла (Telegram лимит 50MB)
        file_size = file_path_obj.stat().st_size
        if file_size > 50 * 1024 * 1024:  # 50MB в байтах
            size_mb = file_size / (1024 * 1024)
            await callback.message.answer(
                f"📊 **{title}**\n"
                f"Файл слишком большой для отправки ({size_mb:.1f} MB > 50 MB)\n"
                f"📁 Файл: `{file_path_obj.name}`",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ]),
                parse_mode='Markdown'
            )
            await log_file_download(callback.from_user.id, file_path, title, False)
            await callback.answer()
            return
        
        # Отправляем файл
        try:
            original_filename = doc_info.get('original_filename', '')
            send_filename = original_filename if original_filename else file_path_obj.name
            if not send_filename.lower().endswith(f'.{file_type.lower()}'):
                send_filename += f'.{file_type.lower()}'
            
            file_input = FSInputFile(
                path=str(file_path_obj),
                filename=send_filename
            )
            
            caption = f"📄 **{title}**"
            
            await callback.message.answer_document(
                document=file_input,
                caption=caption,
                parse_mode='Markdown'
            )
            
            await callback.message.answer(
                "✅ Документ успешно отправлен!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
                ])
            )
            
            logger.info(f"Документ успешно отправлен пользователю {callback.from_user.id}: {title}")
            await log_file_download(callback.from_user.id, file_path, title, True)
            
        except Exception as send_error:
            logger.error(f"Ошибка отправки документа {title}: {send_error}")
            await callback.message.answer(
                f"❌ **{title}**\nОшибка при отправке файла",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
                ])
            )
            await log_file_download(callback.from_user.id, file_path, title, False)
        
    except Exception as e:
        logger.error(f"Ошибка в download_doc_callback: {e}")
        await callback.message.answer(
            "❌ Произошла ошибка при попытке скачивания документа",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К документам", callback_data="show_documents")]
            ])
        )
    
    await callback.answer()

@router.callback_query(F.data == "current_page")
async def current_page_callback(callback: CallbackQuery):
    """Обработчик клика по индикатору текущей страницы (ничего не делаем)"""
    await callback.answer()

def register_handlers(dp: Dispatcher):
    """
    Регистрация всех обработчиков
    
    Args:
        dp: Диспетчер aiogram
    """
    # Подключаем роутер
    dp.include_router(router)
    
    logger.info("✅ Все обработчики зарегистрированы") 