"""
Утилиты для работы с файлами в Telegram боте
"""

import os
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

def normalize_file_path(file_path: str) -> str:
    """
    Нормализует путь к файлу для корректной работы в Docker окружении.
    
    Эта функция решает проблему с путями документов, обеспечивая
    надежную работу независимо от того, как сохранены пути в БД.
    """
    if not file_path:
        return ""
    
    # Определяем базовую папку uploads в зависимости от окружения
    if os.getenv("DOCKER_ENV") or os.path.exists("/app/uploads"):
        base_uploads_dir = "/app/uploads"
    else:
        # Fallback для локальной разработки
        base_uploads_dir = str(Path(__file__).parent.parent.parent / "services" / "admin-panel" / "uploads")
    
    # Если путь уже абсолютный и существует, возвращаем как есть
    file_path_obj = Path(file_path)
    if file_path_obj.is_absolute() and file_path_obj.exists():
        return str(file_path_obj)
    
    # Если путь абсолютный, но файл не найден, пробуем найти файл по имени
    if file_path_obj.is_absolute():
        filename = file_path_obj.name
        normalized_path = Path(base_uploads_dir) / filename
        if normalized_path.exists():
            logger.info(f"Файл найден по нормализованному пути: {normalized_path}")
            return str(normalized_path)
    
    # Если путь относительный, строим абсолютный
    if not file_path_obj.is_absolute():
        normalized_path = Path(base_uploads_dir) / file_path
        if normalized_path.exists():
            return str(normalized_path)
    
    # Если ничего не помогло, пробуем найти файл по имени в uploads
    filename = file_path_obj.name
    uploads_path = Path(base_uploads_dir)
    if uploads_path.exists():
        for existing_file in uploads_path.iterdir():
            if existing_file.name == filename:
                logger.info(f"Файл найден в uploads по имени: {existing_file}")
                return str(existing_file)
    
    # Возвращаем исходный путь если ничего не найдено
    logger.warning(f"Не удалось нормализовать путь к файлу: {file_path}")
    return file_path

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

def validate_file_access(file_path: str, file_type: str, title: str) -> Tuple[bool, str]:
    """
    Комплексная проверка файла перед отправкой пользователю.
    
    Returns:
        Tuple[bool, str]: (можно_ли_отправлять, причина_если_нельзя)
    """
    # Нормализуем путь
    normalized_path = normalize_file_path(file_path)
    
    # Проверяем существование файла
    if not Path(normalized_path).exists():
        return False, f"Файл не найден: {Path(normalized_path).name}"
    
    # Проверяем безопасность
    if not is_file_allowed_for_sharing(normalized_path, file_type):
        return False, "Файл недоступен для отправки по соображениям безопасности"
    
    # Проверяем размер (Telegram лимит 50MB)
    try:
        file_size = Path(normalized_path).stat().st_size
        if file_size > 50 * 1024 * 1024:  # 50MB
            size_mb = file_size / (1024 * 1024)
            return False, f"Файл слишком большой ({size_mb:.1f} MB > 50 MB)"
    except Exception as e:
        return False, f"Ошибка чтения файла: {str(e)}"
    
    return True, "" 