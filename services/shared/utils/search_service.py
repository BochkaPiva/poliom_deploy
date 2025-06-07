#!/usr/bin/env python3
"""
Сервис поиска по документам с LLM форматированием
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from sqlalchemy.orm import Session

# Исправляем импорты на абсолютные
try:
    from services.shared.utils.embeddings import EmbeddingService
    from services.shared.utils.llm_service import LLMService
    from services.shared.models.database import SessionLocal
    from services.shared.models.document import DocumentChunk, Document
except ImportError:
    # Fallback для случая, если модули не найдены
    from utils.embeddings import EmbeddingService
    from utils.llm_service import LLMService
    from models.database import SessionLocal
    from models.document import DocumentChunk, Document

logger = logging.getLogger(__name__)

class SearchService:
    """Сервис для поиска по документам"""
    
    def __init__(self):
        """Инициализация сервиса"""
        self.embedding_service = EmbeddingService()
        self.llm_service = LLMService()
    
    def search(self, query: str, max_results: int = 5, min_similarity: float = 0.3) -> Dict[str, Any]:
        """
        Выполняет поиск по документам
        
        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов
            min_similarity: Минимальная схожесть для включения в результаты
        
        Returns:
            Словарь с результатами поиска и отформатированным ответом
        """
        try:
            # Создаем эмбеддинг для запроса
            query_embedding = self.embedding_service.create_embedding(query)
            
            # Получаем результаты поиска
            search_results = self._perform_search(
                query_embedding, max_results, min_similarity
            )
            
            if not search_results:
                return {
                    'query': query,
                    'results': [],
                    'formatted_answer': "❌ К сожалению, информация по вашему запросу не найдена.",
                    'total_found': 0,
                    'search_quality': 'no_results'
                }
            
            # Форматируем ответ с помощью LLM
            formatted_answer = self.llm_service.format_search_answer(query, search_results)
            
            # Определяем качество поиска
            best_similarity = search_results[0]['similarity'] if search_results else 0
            search_quality = self._determine_search_quality(best_similarity)
            
            return {
                'query': query,
                'results': search_results,
                'formatted_answer': formatted_answer,
                'total_found': len(search_results),
                'search_quality': search_quality,
                'best_similarity': best_similarity
            }
            
        except Exception as e:
            logger.error(f"Ошибка при поиске: {e}")
            return {
                'query': query,
                'results': [],
                'formatted_answer': f"❌ Произошла ошибка при поиске: {str(e)}",
                'total_found': 0,
                'search_quality': 'error'
            }
    
    def _perform_search(self, query_embedding: List[float], max_results: int, min_similarity: float) -> List[Dict[str, Any]]:
        """
        Выполняет поиск по эмбеддингам
        """
        session = SessionLocal()
        try:
            # Получаем все чанки с эмбеддингами
            chunks = session.query(DocumentChunk).join(Document).filter(
                DocumentChunk.embedding_vector.isnot(None)
            ).all()
            
            if not chunks:
                return []
            
            # Вычисляем схожесть для каждого чанка
            similarities = []
            query_embedding_np = np.array(query_embedding)
            
            for chunk in chunks:
                try:
                    chunk_embedding = np.array(chunk.embedding_vector)
                    
                    # Косинусная схожесть
                    similarity = np.dot(query_embedding_np, chunk_embedding) / (
                        np.linalg.norm(query_embedding_np) * np.linalg.norm(chunk_embedding)
                    )
                    
                    if similarity >= min_similarity:
                        similarities.append({
                            'chunk_id': chunk.id,
                            'content': chunk.content,
                            'similarity': float(similarity),
                            'document_name': chunk.document.original_filename,
                            'document_id': chunk.document.id,
                            'chunk_index': chunk.chunk_index,
                            'content_length': chunk.content_length
                        })
                        
                except Exception as e:
                    logger.warning(f"Ошибка при обработке чанка {chunk.id}: {e}")
                    continue
            
            # Сортируем по убыванию схожести
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            
            return similarities[:max_results]
            
        finally:
            session.close()
    
    def _determine_search_quality(self, similarity: float) -> str:
        """
        Определяет качество поиска на основе схожести
        """
        if similarity >= 0.7:
            return 'excellent'
        elif similarity >= 0.6:
            return 'good'
        elif similarity >= 0.5:
            return 'fair'
        elif similarity >= 0.3:
            return 'poor'
        else:
            return 'very_poor'
    
    def search_with_context(self, query: str, context_size: int = 3) -> Dict[str, Any]:
        """
        Поиск с расширенным контекстом (соседние чанки)
        """
        try:
            # Выполняем обычный поиск
            search_result = self.search(query, max_results=1)
            
            if not search_result['results']:
                return search_result
            
            best_result = search_result['results'][0]
            
            # Получаем соседние чанки для контекста
            context_chunks = self._get_context_chunks(
                best_result['document_id'],
                best_result['chunk_index'],
                context_size
            )
            
            # Объединяем контекст
            full_context = self._merge_context(context_chunks, best_result['chunk_index'])
            
            # Создаем расширенный результат
            extended_result = {
                **search_result,
                'context': full_context,
                'context_chunks': context_chunks
            }
            
            # Переформатируем ответ с учетом контекста
            if context_chunks:
                context_results = [
                    {
                        'content': chunk['content'],
                        'similarity': 1.0 if chunk['chunk_index'] == best_result['chunk_index'] else 0.8,
                        'document_name': best_result['document_name'],
                        'chunk_index': chunk['chunk_index']
                    }
                    for chunk in context_chunks
                ]
                
                extended_result['formatted_answer'] = self.llm_service.format_search_answer(
                    query, context_results
                )
            
            return extended_result
            
        except Exception as e:
            logger.error(f"Ошибка при поиске с контекстом: {e}")
            return self.search(query)  # Fallback к обычному поиску
    
    def _get_context_chunks(self, document_id: int, chunk_index: int, context_size: int) -> List[Dict[str, Any]]:
        """
        Получает соседние чанки для контекста
        """
        session = SessionLocal()
        try:
            # Определяем диапазон чанков
            start_index = max(0, chunk_index - context_size)
            end_index = chunk_index + context_size + 1
            
            # Получаем чанки в диапазоне
            chunks = session.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.chunk_index >= start_index,
                DocumentChunk.chunk_index < end_index
            ).order_by(DocumentChunk.chunk_index).all()
            
            return [
                {
                    'chunk_index': chunk.chunk_index,
                    'content': chunk.content,
                    'content_length': chunk.content_length
                }
                for chunk in chunks
            ]
            
        finally:
            session.close()
    
    def _merge_context(self, context_chunks: List[Dict[str, Any]], target_index: int) -> str:
        """
        Объединяет контекстные чанки в единый текст
        """
        if not context_chunks:
            return ""
        
        # Сортируем по индексу
        sorted_chunks = sorted(context_chunks, key=lambda x: x['chunk_index'])
        
        # Объединяем тексты
        merged_parts = []
        for chunk in sorted_chunks:
            if chunk['chunk_index'] == target_index:
                # Выделяем целевой чанк
                merged_parts.append(f"**{chunk['content']}**")
            else:
                merged_parts.append(chunk['content'])
        
        return " ".join(merged_parts)
    
    def get_search_suggestions(self, partial_query: str) -> List[str]:
        """
        Возвращает предложения для автодополнения поиска
        """
        # Базовые предложения по темам
        suggestions = [
            "размер заработной платы",
            "доплата за ночную работу",
            "надбавка за вахтовый метод",
            "оплата в праздничные дни",
            "вредные условия труда",
            "сверхурочная работа",
            "отпускные выплаты",
            "больничный лист",
            "командировочные расходы",
            "премии и надбавки"
        ]
        
        # Фильтруем по частичному запросу
        if partial_query:
            filtered = [s for s in suggestions if partial_query.lower() in s.lower()]
            return filtered[:5]
        
        return suggestions[:5] 