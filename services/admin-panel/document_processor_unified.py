#!/usr/bin/env python3
"""
ЕДИНЫЙ МОДУЛЬ ОБРАБОТКИ ДОКУМЕНТОВ
Надежное решение для обработки документов с улучшенным алгоритмом чанкинга
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

# Добавляем путь к services
services_path = Path(__file__).parent.parent
sys.path.append(str(services_path))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv('.env.local')

from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import text
from shared.models.database import engine
from shared.models import Document, DocumentChunk
from shared.utils.document_processor import DocumentProcessor
from shared.utils.embeddings import EmbeddingService

# Создаем сессию базы данных
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DocumentProcessorUnified:
    """
    ЕДИНЫЙ ПРОЦЕССОР ДОКУМЕНТОВ
    Надежная обработка с улучшенным алгоритмом чанкинга
    """
    
    def __init__(self):
        self.document_processor = DocumentProcessor()
        self.embedding_service = EmbeddingService()
    
    def improved_split_into_chunks(self, text: str, chunk_size: int = 1500, overlap: int = 200) -> List[str]:
        """
        УЛУЧШЕННЫЙ алгоритм разбиения текста на чанки
        Учитывает границы предложений и создает качественные чанки
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
    
    def safe_delete_old_chunks(self, db: Session, document_id: int) -> bool:
        """
        БЕЗОПАСНОЕ удаление старых чанков
        Использует SQL для обхода проблем с SQLAlchemy
        """
        try:
            logger.info(f"Удаляем старые чанки для документа {document_id}")
            
            # Сначала пробуем через SQLAlchemy
            try:
                old_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
                if old_chunks:
                    logger.info(f"Найдено {len(old_chunks)} старых чанков")
                    for chunk in old_chunks:
                        db.delete(chunk)
                    db.commit()
                    logger.info("Старые чанки удалены через SQLAlchemy")
                    return True
            except Exception as e:
                logger.warning(f"SQLAlchemy удаление не удалось: {e}")
                db.rollback()
                
                # Fallback: используем прямой SQL
                try:
                    db.execute(text("DELETE FROM document_chunks WHERE document_id = :doc_id"), {"doc_id": document_id})
                    db.commit()
                    logger.info("Старые чанки удалены через SQL")
                    return True
                except Exception as sql_error:
                    logger.error(f"SQL удаление тоже не удалось: {sql_error}")
                    db.rollback()
                    return False
            
        except Exception as e:
            logger.error(f"Ошибка удаления старых чанков: {e}")
            return False
    
    def process_document(self, document_id: int, use_safe_mode: bool = True) -> dict:
        """
        ГЛАВНАЯ ФУНКЦИЯ обработки документа
        
        Args:
            document_id: ID документа для обработки
            use_safe_mode: Использовать безопасный режим (обход проблем PostgreSQL)
        
        Returns:
            dict: Результат обработки
        """
        logger.info(f"Начинаем обработку документа {document_id} (safe_mode={use_safe_mode})")
        
        db = SessionLocal()
        try:
            # Получаем документ из базы данных
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                error_msg = f"Документ {document_id} не найден"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            logger.info(f"Обрабатываем документ: {document.original_filename}")
            
            # Проверяем, что файл существует
            file_path = Path(document.file_path)
            if not file_path.exists():
                error_msg = f"Файл не найден: {document.file_path}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}
            
            logger.info(f"Файл найден: {file_path.stat().st_size} байт")
            
            # Обновляем статус на "processing"
            document.processing_status = "processing"
            document.updated_at = datetime.utcnow()
            db.commit()
            logger.info("Статус изменен на 'processing'")
            
            # Удаляем старые чанки
            if not self.safe_delete_old_chunks(db, document_id):
                logger.warning("Не удалось удалить старые чанки, продолжаем...")
            
            # Извлекаем текст из документа
            logger.info("Извлекаем текст из документа...")
            text_content = self.document_processor.extract_text(document.file_path)
            if not text_content or not text_content.strip():
                raise Exception("Не удалось извлечь текст из документа")
            
            logger.info(f"Текст извлечен: {len(text_content)} символов")
            
            # Разбиваем текст на чанки с УЛУЧШЕННЫМ алгоритмом
            logger.info("Разбиваем текст на чанки (улучшенный алгоритм)...")
            chunks = self.improved_split_into_chunks(text_content, chunk_size=1500, overlap=200)
            if not chunks:
                raise Exception("Не удалось разбить документ на чанки")
            
            logger.info(f"Документ разбит на {len(chunks)} качественных чанков")
            
            # Анализируем размеры чанков
            chunk_sizes = [len(chunk) for chunk in chunks]
            logger.info(f"Статистика чанков: мин={min(chunk_sizes)}, макс={max(chunk_sizes)}, средний={sum(chunk_sizes)/len(chunk_sizes):.1f}")
            
            # Создаем чанки в базе данных
            logger.info("Создаем чанки в базе данных...")
            created_chunks = []
            
            for i, chunk_text in enumerate(chunks):
                try:
                    logger.debug(f"Обрабатываем чанк {i+1}/{len(chunks)}")
                    
                    # Генерируем эмбеддинг для чанка
                    embedding = self.embedding_service.get_embedding(chunk_text)
                    
                    # Создаем чанк в базе данных
                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=i,
                        content=chunk_text,
                        content_length=len(chunk_text),
                        embedding_vector=embedding,
                        created_at=datetime.utcnow()
                    )
                    
                    db.add(chunk)
                    created_chunks.append(chunk)
                    
                    # Коммитим каждые 5 чанков для избежания проблем с памятью
                    if (i + 1) % 5 == 0:
                        db.commit()
                        logger.debug(f"Сохранено {i+1} чанков...")
                    
                except Exception as e:
                    logger.error(f"Ошибка создания чанка {i}: {str(e)}")
                    continue
            
            if not created_chunks:
                raise Exception("Не удалось создать ни одного чанка")
            
            # Финальное сохранение
            logger.info("Финальное сохранение чанков...")
            db.commit()
            
            # Обновляем статус документа на "completed"
            document.processing_status = "completed"
            document.processed_at = datetime.utcnow()
            document.updated_at = datetime.utcnow()
            document.chunks_count = len(created_chunks)
            db.commit()
            
            success_msg = f"Документ {document_id} успешно обработан. Создано {len(created_chunks)} качественных чанков"
            logger.info(success_msg)
            
            return {
                "status": "completed",
                "document_id": document_id,
                "filename": document.original_filename,
                "chunks_created": len(created_chunks),
                "chunk_stats": {
                    "min_size": min(chunk_sizes),
                    "max_size": max(chunk_sizes),
                    "avg_size": sum(chunk_sizes) / len(chunk_sizes)
                },
                "message": success_msg
            }
            
        except Exception as e:
            error_msg = f"Ошибка обработки документа {document_id}: {str(e)}"
            logger.error(error_msg)
            
            # Обновляем статус документа на "failed"
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document.processing_status = "failed"
                    document.error_message = str(e)
                    document.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info("Статус изменен на 'failed'")
            except Exception as db_error:
                logger.error(f"Ошибка обновления статуса: {str(db_error)}")
            
            return {
                "status": "failed",
                "document_id": document_id,
                "error": str(e)
            }
            
        finally:
            db.close()
    
    def process_all_pending_documents(self) -> dict:
        """
        Обрабатывает все необработанные документы
        """
        logger.info("Начинаем обработку всех необработанных документов")
        
        db = SessionLocal()
        try:
            # Ищем документы со статусом uploaded, pending или failed
            pending_docs = db.query(Document).filter(
                Document.processing_status.in_(['uploaded', 'pending', 'failed'])
            ).all()
            
            if not pending_docs:
                logger.info("Все документы уже обработаны")
                return {"status": "completed", "message": "Все документы уже обработаны", "processed": 0}
            
            logger.info(f"Найдено необработанных документов: {len(pending_docs)}")
            
            success_count = 0
            error_count = 0
            results = []
            
            for doc in pending_docs:
                logger.info(f"Обрабатываем документ {doc.id}: {doc.original_filename}")
                
                result = self.process_document(doc.id, use_safe_mode=True)
                results.append(result)
                
                if result["status"] == "completed":
                    success_count += 1
                    logger.info(f"✅ Документ {doc.id} успешно обработан")
                else:
                    error_count += 1
                    logger.error(f"❌ Ошибка обработки документа {doc.id}: {result.get('error', 'Unknown error')}")
            
            summary = {
                "status": "completed",
                "total_documents": len(pending_docs),
                "successful": success_count,
                "failed": error_count,
                "results": results,
                "message": f"Обработка завершена: {success_count} успешно, {error_count} с ошибками"
            }
            
            logger.info(summary["message"])
            return summary
            
        except Exception as e:
            error_msg = f"Ошибка массовой обработки документов: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
            
        finally:
            db.close()
    
    def get_document_status(self, document_id: Optional[int] = None) -> dict:
        """
        Получает статус документа(ов)
        """
        db = SessionLocal()
        try:
            if document_id:
                # Статус конкретного документа
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    return {"status": "error", "message": f"Документ {document_id} не найден"}
                
                return {
                    "status": "success",
                    "document": {
                        "id": document.id,
                        "filename": document.original_filename,
                        "processing_status": document.processing_status,
                        "chunks_count": document.chunks_count or 0,
                        "created_at": document.created_at,
                        "processed_at": document.processed_at,
                        "error_message": document.error_message
                    }
                }
            else:
                # Статус всех документов
                documents = db.query(Document).all()
                
                stats = {
                    "total": len(documents),
                    "completed": len([d for d in documents if d.processing_status == "completed"]),
                    "failed": len([d for d in documents if d.processing_status == "failed"]),
                    "pending": len([d for d in documents if d.processing_status in ["uploaded", "pending", "processing"]])
                }
                
                return {
                    "status": "success",
                    "statistics": stats,
                    "documents": [
                        {
                            "id": doc.id,
                            "filename": doc.original_filename,
                            "processing_status": doc.processing_status,
                            "chunks_count": doc.chunks_count or 0,
                            "created_at": doc.created_at,
                            "processed_at": doc.processed_at
                        }
                        for doc in documents
                    ]
                }
                
        except Exception as e:
            error_msg = f"Ошибка получения статуса: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
            
        finally:
            db.close()


# Глобальная переменная для ленивой инициализации
_unified_processor = None


def get_unified_processor():
    """
    Получает экземпляр процессора с ленивой инициализацией
    Модель загружается только при первом обращении
    """
    global _unified_processor
    if _unified_processor is None:
        logger.info("Инициализируем единый процессор документов...")
        _unified_processor = DocumentProcessorUnified()
        logger.info("Единый процессор документов готов к работе")
    return _unified_processor


def process_document_unified(document_id: int, use_safe_mode: bool = True) -> dict:
    """
    ГЛАВНАЯ ФУНКЦИЯ для обработки документа
    Используйте эту функцию везде в проекте
    """
    processor = get_unified_processor()
    return processor.process_document(document_id, use_safe_mode)


def process_all_pending_unified() -> dict:
    """
    ГЛАВНАЯ ФУНКЦИЯ для обработки всех необработанных документов
    """
    processor = get_unified_processor()
    return processor.process_all_pending_documents()


def get_documents_status_unified(document_id: Optional[int] = None) -> dict:
    """
    ГЛАВНАЯ ФУНКЦИЯ для получения статуса документов
    """
    processor = get_unified_processor()
    return processor.get_document_status(document_id)


if __name__ == "__main__":
    # Если запускается как скрипт, обрабатываем все необработанные документы
    print("🚀 ЕДИНЫЙ ПРОЦЕССОР ДОКУМЕНТОВ")
    print("=" * 60)
    
    # Показываем текущий статус
    status = get_documents_status_unified()
    if status["status"] == "success":
        stats = status["statistics"]
        print(f"📊 Статус документов:")
        print(f"   Всего: {stats['total']}")
        print(f"   Обработано: {stats['completed']}")
        print(f"   Ошибок: {stats['failed']}")
        print(f"   Ожидают: {stats['pending']}")
        print()
    
    # Обрабатываем необработанные документы
    if status["status"] == "success" and status["statistics"]["pending"] > 0:
        print("🔄 Обрабатываем необработанные документы...")
        result = process_all_pending_unified()
        print(f"✅ {result['message']}")
    else:
        print("✅ Все документы уже обработаны") 