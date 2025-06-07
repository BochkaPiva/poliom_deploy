"""
Утилита для обработки документов
"""

import os
import logging
from pathlib import Path
from typing import List, Optional
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    magic = None
import PyPDF2
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Класс для обработки различных типов документов"""
    
    def __init__(self):
        self.supported_types = {
            'pdf': self._extract_pdf_text,
            'docx': self._extract_docx_text,
            'doc': self._extract_doc_text,
            'txt': self._extract_txt_text
        }
    
    def extract_text(self, file_path: str) -> str:
        """
        Извлекает текст из документа
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Извлеченный текст
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"Файл не найден: {file_path}")
            
            # Определяем тип файла по расширению
            file_ext = file_path.suffix.lower().lstrip('.')
            
            if file_ext not in self.supported_types:
                raise ValueError(f"Неподдерживаемый тип файла: {file_ext}")
            
            # Извлекаем текст
            text = self.supported_types[file_ext](file_path)
            
            if not text or not text.strip():
                raise ValueError("Не удалось извлечь текст из документа")
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Ошибка извлечения текста из {file_path}: {str(e)}")
            raise
    
    def _extract_pdf_text(self, file_path: Path) -> str:
        """Извлекает текст из PDF файла"""
        text = ""
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text() + "\n"
                    
        except Exception as e:
            logger.error(f"Ошибка чтения PDF файла {file_path}: {str(e)}")
            raise
        
        return text
    
    def _extract_docx_text(self, file_path: Path) -> str:
        """Извлекает текст из DOCX файла"""
        text = ""
        
        try:
            doc = DocxDocument(file_path)
            
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
                
        except Exception as e:
            logger.error(f"Ошибка чтения DOCX файла {file_path}: {str(e)}")
            raise
        
        return text
    
    def _extract_doc_text(self, file_path: Path) -> str:
        """Извлекает текст из DOC файла (старый формат Word)"""
        # Для DOC файлов нужны дополнительные библиотеки
        # Пока возвращаем ошибку
        raise NotImplementedError("Обработка DOC файлов пока не поддерживается. Используйте DOCX формат.")
    
    def _extract_txt_text(self, file_path: Path) -> str:
        """Извлекает текст из TXT файла"""
        try:
            # Пробуем разные кодировки
            encodings = ['utf-8', 'cp1251', 'latin-1']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as file:
                        return file.read()
                except UnicodeDecodeError:
                    continue
            
            raise ValueError("Не удалось определить кодировку файла")
            
        except Exception as e:
            logger.error(f"Ошибка чтения TXT файла {file_path}: {str(e)}")
            raise
    
    def split_into_chunks(self, text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
        """
        УЛУЧШЕННЫЙ алгоритм разбиения текста на чанки
        Учитывает границы предложений и создает качественные чанки
        
        Args:
            text: Исходный текст
            chunk_size: Размер чанка в символах
            overlap: Перекрытие между чанками
            
        Returns:
            Список чанков
        """
        if not text or not text.strip():
            return []
        
        text = text.strip()
        
        # Если текст короткий, возвращаем его как один чанк
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Определяем конец текущего чанка
            end = min(start + chunk_size, len(text))
            
            # Если это не последний чанк, ищем хорошее место для разрыва
            if end < len(text):
                # Ищем ближайшую границу предложения в последних 200 символах чанка
                search_start = max(start, end - 200)
                
                # Ищем разделители в порядке приоритета
                best_break = -1
                
                # 1. Точка с пробелом
                for i in range(end - 1, search_start - 1, -1):
                    if i < len(text) - 1 and text[i] == '.' and text[i + 1] == ' ':
                        best_break = i + 1
                        break
                
                # 2. Восклицательный или вопросительный знак с пробелом
                if best_break == -1:
                    for i in range(end - 1, search_start - 1, -1):
                        if i < len(text) - 1 and text[i] in '!?' and text[i + 1] == ' ':
                            best_break = i + 1
                            break
                
                # 3. Двойной перенос строки
                if best_break == -1:
                    double_newline = text.rfind('\n\n', search_start, end)
                    if double_newline != -1:
                        best_break = double_newline + 2
                
                # 4. Одинарный перенос строки
                if best_break == -1:
                    newline = text.rfind('\n', search_start, end)
                    if newline != -1:
                        best_break = newline + 1
                
                # 5. Пробел (последний вариант)
                if best_break == -1:
                    space = text.rfind(' ', search_start, end)
                    if space != -1:
                        best_break = space + 1
                
                # Если нашли хорошее место для разрыва, используем его
                if best_break != -1:
                    end = best_break
            
            # Извлекаем чанк
            chunk = text[start:end].strip()
            
            # Добавляем чанк только если он не пустой и достаточно длинный
            if chunk and len(chunk) > 10:  # Минимум 10 символов
                chunks.append(chunk)
            
            # Вычисляем начало следующего чанка
            if end >= len(text):
                break
            
            # Следующий чанк начинается с учетом перекрытия
            # НО не раньше чем через минимальный шаг
            min_step = max(50, chunk_size // 4)  # Минимальный шаг - 50 символов или 1/4 размера чанка
            next_start = max(start + min_step, end - overlap)
            
            # Убеждаемся, что мы продвигаемся вперед
            if next_start <= start:
                next_start = start + min_step
            
            start = next_start
        
        return chunks
    
    def validate_file(self, file_path: str, max_size: int = 50 * 1024 * 1024) -> bool:
        """
        Валидирует файл
        
        Args:
            file_path: Путь к файлу
            max_size: Максимальный размер файла в байтах
            
        Returns:
            True если файл валиден
        """
        try:
            file_path = Path(file_path)
            
            # Проверяем существование файла
            if not file_path.exists():
                raise FileNotFoundError(f"Файл не найден: {file_path}")
            
            # Проверяем размер файла
            file_size = file_path.stat().st_size
            if file_size > max_size:
                raise ValueError(f"Файл слишком большой: {file_size} байт (максимум: {max_size})")
            
            # Проверяем расширение
            file_ext = file_path.suffix.lower().lstrip('.')
            if file_ext not in self.supported_types:
                raise ValueError(f"Неподдерживаемый тип файла: {file_ext}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка валидации файла {file_path}: {str(e)}")
            raise 