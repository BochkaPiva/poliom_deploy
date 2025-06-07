"""
Обработчики системных команд для администратора
"""

import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from .config import config

logger = logging.getLogger(__name__)

system_router = Router()

@system_router.message(Command("system_health"))
async def system_health_handler(message: Message):
    """Обработчик команды проверки состояния системы"""
    user_id = message.from_user.id
    
    # Проверяем, что пользователь администратор
    if user_id != config.ADMIN_USER_ID:
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return
    
    try:
        # Показываем процесс проверки
        status_message = await message.reply("🔍 Проверяю состояние системы...")
        
        # Запускаем проверку
        from .system_monitor import system_monitor
        health_report = await system_monitor.generate_health_report()
        
        # Отправляем отчет
        await status_message.edit_text(health_report, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка проверки состояния системы: {e}")
        await message.reply("❌ Произошла ошибка при проверке системы.")

@system_router.message(Command("auto_fix"))
async def auto_fix_handler(message: Message):
    """Обработчик автоматического исправления проблем"""
    user_id = message.from_user.id
    
    # Проверяем, что пользователь администратор
    if user_id != config.ADMIN_USER_ID:
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return
    
    try:
        # Показываем процесс исправления
        status_message = await message.reply("🔧 Запускаю автоматическое исправление...")
        
        # Запускаем исправление
        from .system_monitor import system_monitor
        fixes_count = await system_monitor.auto_fix_common_issues()
        
        if fixes_count > 0:
            await status_message.edit_text(f"✅ Исправлено проблем: {fixes_count}")
        else:
            await status_message.edit_text("ℹ️ Проблем для автоматического исправления не найдено.")
            
    except Exception as e:
        logger.error(f"Ошибка автоматического исправления: {e}")
        await message.reply("❌ Произошла ошибка при исправлении.")

@system_router.callback_query(F.data == "auto_fix_system")
async def auto_fix_system_callback(callback: CallbackQuery):
    """Callback для автоматического исправления системных проблем"""
    user_id = callback.from_user.id
    
    # Проверяем, что пользователь администратор
    if user_id != config.ADMIN_USER_ID:
        await callback.answer("❌ У вас нет прав для выполнения этой команды.", show_alert=True)
        return
    
    try:
        # Показываем процесс исправления
        await callback.message.edit_text("🔧 Запускаю автоматическое исправление...")
        
        # Запускаем исправление
        from .system_monitor import system_monitor
        fixes_count = await system_monitor.auto_fix_common_issues()
        
        if fixes_count > 0:
            message_text = f"✅ Исправлено проблем: {fixes_count}"
        else:
            message_text = "ℹ️ Проблем для автоматического исправления не найдено."
            
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(message_text, reply_markup=back_keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка автоматического исправления: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при исправлении.")
    
    await callback.answer()

@system_router.callback_query(F.data == "system_health_check")
async def system_health_check_callback(callback: CallbackQuery):
    """Callback для проверки состояния системы"""
    user_id = callback.from_user.id
    
    # Проверяем, что пользователь администратор
    if user_id != config.ADMIN_USER_ID:
        await callback.answer("❌ У вас нет прав для выполнения этой команды.", show_alert=True)
        return
    
    try:
        # Показываем процесс проверки
        await callback.message.edit_text("🔍 Проверяю состояние системы...")
        
        # Запускаем проверку
        from .system_monitor import system_monitor
        health_report = await system_monitor.generate_health_report()
        
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔧 Исправить ошибки", callback_data="auto_fix_system")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ])
        
        # Отправляем отчет
        await callback.message.edit_text(health_report, reply_markup=back_keyboard, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка проверки состояния системы: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при проверке системы.")
    
    await callback.answer() 