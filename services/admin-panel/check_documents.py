#!/usr/bin/env python3
"""
Диагностический скрипт для проверки документов в базе данных
"""

import os
import sys
from pathlib import Path

# Добавляем путь к services
services_path = Path(__file__).parent.parent
sys.path.append(str(services_path))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv('.env.local')

from sqlalchemy.orm import sessionmaker
from shared.models.database import engine
from shared.models import Document, DocumentChunk

# Создаем сессию базы данных
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_documents():
    """Проверяем все документы в базе данных"""
    print("📋 ПРОВЕРКА ДОКУМЕНТОВ В БАЗЕ ДАННЫХ")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Получаем все документы
        documents = db.query(Document).all()
        
        if not documents:
            print("❌ Документы не найдены в базе данных")
            return
        
        print(f"📊 Найдено документов: {len(documents)}")
        print()
        
        for doc in documents:
            print(f"📄 Документ ID {doc.id}: {doc.original_filename}")
            print(f"   📁 Путь: {doc.file_path}")
            print(f"   📊 Статус: {doc.processing_status}")
            print(f"   📈 Размер файла: {doc.file_size} байт")
            print(f"   🗓️ Загружен: {doc.created_at}")
            
            if doc.processed_at:
                print(f"   ✅ Обработан: {doc.processed_at}")
            
            if doc.chunks_count:
                print(f"   📦 Чанков: {doc.chunks_count}")
            
            if doc.error_message:
                print(f"   ❌ Ошибка: {doc.error_message}")
            
            # Проверяем существование файла
            file_path = Path(doc.file_path)
            if file_path.exists():
                actual_size = file_path.stat().st_size
                print(f"   ✅ Файл существует (размер: {actual_size} байт)")
                if actual_size != doc.file_size:
                    print(f"   ⚠️ ВНИМАНИЕ: Размер файла не совпадает с БД!")
            else:
                print(f"   ❌ ФАЙЛ НЕ НАЙДЕН: {doc.file_path}")
            
            # Проверяем чанки
            chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).all()
            actual_chunks = len(chunks)
            
            if actual_chunks > 0:
                print(f"   📦 Фактически чанков в БД: {actual_chunks}")
                if doc.chunks_count != actual_chunks:
                    print(f"   ⚠️ ВНИМАНИЕ: Количество чанков не совпадает!")
                
                # Статистика размеров чанков
                chunk_sizes = [len(chunk.content) for chunk in chunks]
                if chunk_sizes:
                    print(f"   📏 Размеры чанков: мин={min(chunk_sizes)}, макс={max(chunk_sizes)}, средний={sum(chunk_sizes)/len(chunk_sizes):.1f}")
            else:
                print(f"   📦 Чанки в БД: отсутствуют")
            
            print()
        
        # Общая статистика
        print("=" * 60)
        print("📊 ОБЩАЯ СТАТИСТИКА:")
        
        statuses = {}
        total_chunks = 0
        total_size = 0
        
        for doc in documents:
            status = doc.processing_status
            statuses[status] = statuses.get(status, 0) + 1
            
            if doc.chunks_count:
                total_chunks += doc.chunks_count
            
            if doc.file_size:
                total_size += doc.file_size
        
        print(f"📄 Всего документов: {len(documents)}")
        print(f"📦 Всего чанков: {total_chunks}")
        print(f"💾 Общий размер: {total_size:,} байт ({total_size/1024/1024:.2f} МБ)")
        print()
        
        print("📊 По статусам:")
        for status, count in statuses.items():
            print(f"   {status}: {count}")
        
    except Exception as e:
        print(f"❌ Ошибка проверки: {str(e)}")
    
    finally:
        db.close()

def check_specific_document(document_id: int):
    """Детальная проверка конкретного документа"""
    print(f"🔍 ДЕТАЛЬНАЯ ПРОВЕРКА ДОКУМЕНТА ID {document_id}")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Получаем документ
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            print(f"❌ Документ с ID {document_id} не найден")
            return
        
        print(f"📄 Документ: {document.original_filename}")
        print(f"📁 Путь: {document.file_path}")
        print(f"📊 Статус: {document.processing_status}")
        print(f"📈 Размер: {document.file_size} байт")
        print(f"🗓️ Создан: {document.created_at}")
        print(f"🔄 Обновлен: {document.updated_at}")
        
        if document.processed_at:
            print(f"✅ Обработан: {document.processed_at}")
        
        if document.error_message:
            print(f"❌ Ошибка: {document.error_message}")
        
        print()
        
        # Проверяем файл
        file_path = Path(document.file_path)
        print("📁 ПРОВЕРКА ФАЙЛА:")
        if file_path.exists():
            stat = file_path.stat()
            print(f"   ✅ Файл существует")
            print(f"   📈 Размер: {stat.st_size} байт")
            print(f"   🗓️ Изменен: {stat.st_mtime}")
        else:
            print(f"   ❌ Файл не найден")
        
        print()
        
        # Проверяем чанки
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        print(f"📦 ПРОВЕРКА ЧАНКОВ:")
        print(f"   📊 Количество: {len(chunks)}")
        
        if chunks:
            chunk_sizes = [len(chunk.content) for chunk in chunks]
            print(f"   📏 Размеры: мин={min(chunk_sizes)}, макс={max(chunk_sizes)}, средний={sum(chunk_sizes)/len(chunk_sizes):.1f}")
            
            print(f"   📋 Первые 3 чанка:")
            for i, chunk in enumerate(chunks[:3]):
                preview = chunk.content[:100].replace('\n', ' ')
                print(f"      {i+1}. [{len(chunk.content)} символов] {preview}...")
        else:
            print(f"   📦 Чанки отсутствуют")
    
    except Exception as e:
        print(f"❌ Ошибка проверки документа: {str(e)}")
    
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Проверка документов в базе данных")
    parser.add_argument("--doc-id", type=int, help="ID конкретного документа для детальной проверки")
    
    args = parser.parse_args()
    
    if args.doc_id:
        check_specific_document(args.doc_id)
    else:
        check_documents() 