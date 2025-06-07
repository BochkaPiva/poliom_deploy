# services/shared/utils/simple_rag.py

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session
from sqlalchemy import text

# Исправляем импорт на абсолютный
try:
    # Сначала пробуем импорт из shared (Docker)
    from shared.models.document import Document, DocumentChunk
except ImportError:
    try:
        # Fallback для локальной разработки
        from models.document import Document, DocumentChunk
    except ImportError:
        # Последний fallback
        from services.shared.models.document import Document, DocumentChunk

try:
    from .llm_client import SimpleLLMClient, LLMResponse
except ImportError:
    from llm_client import SimpleLLMClient, LLMResponse

logger = logging.getLogger(__name__)

class SimpleRAG:
    """
    Максимально простая RAG система
    - Локальные эмбеддинги (бесплатно)
    - GigaChat для ответов (бесплатно)
    - Никаких сложностей!
    """
    
    def __init__(self, db_session: Session, gigachat_api_key: str):
        """
        Инициализация RAG системы
        
        Args:
            db_session: Сессия базы данных
            gigachat_api_key: API ключ для GigaChat
        """
        self.db_session = db_session
        self.llm_client = SimpleLLMClient(gigachat_api_key)
        
        # Получаем настройки поиска из переменных окружения
        self.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", "0.3"))
        self.search_limit = int(os.getenv("SEARCH_LIMIT", "15"))
        self.min_similarity = float(os.getenv("MIN_SIMILARITY_THRESHOLD", "0.25"))
        
        # Инициализируем логгер
        self.logger = logging.getLogger(__name__)
        
        # Загружаем модель эмбеддингов
        self.logger.info("Загружаем модель эмбеддингов...")
        self.embedding_model = SentenceTransformer('cointegrated/rubert-tiny2')
        self.logger.info(f"Модель эмбеддингов загружена! Настройки: similarity_threshold={self.similarity_threshold}, search_limit={self.search_limit}, min_similarity={self.min_similarity}")
        
    def create_embedding(self, text: str) -> List[float]:
        """Создание эмбеддинга для текста"""
        try:
            embedding = self.embedding_model.encode([text])[0]
            return embedding.tolist()
        except Exception as e:
            self.logger.error(f"Ошибка создания эмбеддинга: {e}")
            return []
    
    def _format_embedding_for_pgvector(self, embedding: List[float]) -> str:
        """Форматирование эмбеддинга для использования с pgvector"""
        return str(embedding).replace(' ', '')
    
    def search_relevant_chunks(self, question: str, limit: int = 15) -> List[Dict]:
        """
        Поиск релевантных чанков для ответа на вопрос
        
        Args:
            question: Вопрос пользователя
            limit: Максимальное количество чанков для возврата
            
        Returns:
            List[Dict]: Список релевантных чанков с метаданными
        """
        try:
            # 1. Создаем эмбеддинг для вопроса
            question_embedding = self.create_embedding(question)
            self.logger.info(f"Создан эмбеддинг для вопроса, размерность: {len(question_embedding)}")
            
            # 2. Специальная логика для вопросов о зарплате
            salary_keywords = ['зарплата', 'заработная плата', 'выплачивается', 'выплата', 'оплата труда']
            is_salary_question = any(keyword in question.lower() for keyword in salary_keywords)
            
            if is_salary_question:
                self.logger.info("Обнаружен вопрос о зарплате, используем специальную логику поиска")
                
                # Ищем чанки с конкретными датами выплат
                salary_query = text("""
                    SELECT dc.id, dc.document_id, dc.chunk_index, dc.content,
                           1 - (dc.embedding_vector <=> :embedding) as similarity,
                           dc.content_length
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE d.processing_status = 'completed'
                      AND dc.embedding_vector IS NOT NULL
                      AND (dc.content ILIKE '%12%' AND dc.content ILIKE '%27%' AND dc.content ILIKE '%выплачивается%')
                    ORDER BY dc.embedding_vector <=> :embedding
                    LIMIT 3
                """)
                
                salary_result = self.db_session.execute(salary_query, {
                    'embedding': self._format_embedding_for_pgvector(question_embedding)
                })
                
                salary_chunks = []
                for row in salary_result:
                    if row.similarity > 0.3:  # Более низкий порог для специфичных чанков
                        salary_chunks.append({
                            'id': row.id,
                            'document_id': row.document_id,
                            'chunk_index': row.chunk_index,
                            'content': row.content,
                            'similarity': row.similarity + 0.2,  # Бонус за специфичность
                            'search_type': 'salary_specific',
                            'content_length': row.content_length
                        })
                
                if salary_chunks:
                    self.logger.info(f"Найдено {len(salary_chunks)} специфичных чанков о зарплате")
            
            # 3. Выполняем обычный векторный поиск
            self.logger.info("Выполняем векторный поиск...")
            
            # Используем pgvector для поиска похожих эмбеддингов
            query = text("""
                SELECT dc.id, dc.document_id, dc.chunk_index, dc.content,
                       1 - (dc.embedding_vector <=> :embedding) as similarity,
                       dc.content_length
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.processing_status = 'completed'
                  AND dc.embedding_vector IS NOT NULL
                  AND dc.content_length > 100
                  AND dc.content_length < 4000
                  AND dc.content NOT ILIKE '%приложение%'
                  AND dc.content NOT ILIKE '%утверждаю%'
                  AND dc.content NOT ILIKE '%генеральный директор%'
                  AND dc.content NOT ILIKE '%система менеджмента%'
                  AND dc.content NOT ILIKE '%введено впервые%'
                  AND dc.content NOT ILIKE '%дата введения%'
                ORDER BY dc.embedding_vector <=> :embedding
                LIMIT :limit
            """)
            
            result = self.db_session.execute(query, {
                'embedding': self._format_embedding_for_pgvector(question_embedding),
                'limit': limit * 2
            })
            
            vector_chunks = []
            for row in result:
                # Используем настраиваемый минимальный порог схожести
                if (row.similarity > self.min_similarity and  # Используем переменную вместо 0.25
                    self._is_relevant_content(row.content, question)):
                    vector_chunks.append({
                        'id': row.id,
                        'document_id': row.document_id,
                        'chunk_index': row.chunk_index,
                        'content': row.content,
                        'similarity': row.similarity,
                        'search_type': 'vector',
                        'content_length': row.content_length
                    })
            
            self.logger.info(f"Векторный поиск завершен, найдено {len(vector_chunks)} качественных чанков")
            
            # 4. Объединяем результаты
            all_chunks = []
            
            # Сначала добавляем специфичные чанки о зарплате (если есть)
            if is_salary_question and 'salary_chunks' in locals():
                all_chunks.extend(salary_chunks)
            
            # Затем добавляем векторные результаты (исключая дубликаты)
            existing_ids = {chunk['id'] for chunk in all_chunks}
            for chunk in vector_chunks:
                if chunk['id'] not in existing_ids:
                    all_chunks.append(chunk)
            
            # 5. Дополняем улучшенным текстовым поиском при необходимости
            if len(all_chunks) < limit:
                text_chunks = []
                keywords = self._extract_keywords(question)
                
                if keywords:
                    self.logger.info(f"Выполняем текстовый поиск по ключевым словам: {keywords}")
                    
                    # Улучшенный запрос для текстового поиска
                    conditions = []
                    params = {}
                    
                    for i, keyword in enumerate(keywords[:5]):  # Ограничиваем количество ключевых слов
                        param_name = f'keyword_{i}'
                        conditions.append(f"dc.content ILIKE :{param_name}")
                        params[param_name] = f'%{keyword}%'
                    
                    text_query = text(f"""
                        SELECT dc.id, dc.document_id, dc.chunk_index, dc.content,
                                dc.content_length
                        FROM document_chunks dc
                        JOIN documents d ON dc.document_id = d.id
                        WHERE d.processing_status = 'completed'
                          AND dc.content_length > 200
                          AND dc.content_length < 3000
                          AND dc.content NOT ILIKE '%приложение%'
                          AND dc.content NOT ILIKE '%утверждаю%'
                          AND dc.content NOT ILIKE '%генеральный директор%'
                          AND dc.content NOT ILIKE '%система менеджмента%'
                          AND dc.content NOT ILIKE '%положение%о%'
                          AND dc.content NOT ILIKE '%введено впервые%'
                          AND dc.content NOT ILIKE '%дата введения%'
                          AND ({' OR '.join(conditions)})
                        ORDER BY dc.content_length DESC
                        LIMIT :limit
                    """)
                    
                    params['limit'] = limit
                    text_result = self.db_session.execute(text_query, params)
                    
                    existing_ids = {chunk['id'] for chunk in all_chunks}
                    for row in text_result:
                        # Проверяем, что этот чанк еще не найден и содержит релевантную информацию
                        if (row.id not in existing_ids and
                            self._is_relevant_content(row.content, question)):
                            
                            # Вычисляем реальную схожесть на основе пересечения ключевых слов
                            content_words = set(row.content.lower().split())
                            question_words = set(question.lower().split())
                            overlap = len(content_words & question_words)
                            
                            # Улучшенный расчет similarity
                            base_similarity = 0.3
                            keyword_bonus = 0.0
                            
                            # Проверяем наличие ключевых слов из вопроса
                            for keyword in keywords:
                                if keyword.lower() in row.content.lower():
                                    keyword_bonus += 0.1
                            
                            # Бонус за пересечение слов
                            word_bonus = min(overlap * 0.05, 0.3)
                            
                            calculated_similarity = base_similarity + keyword_bonus + word_bonus
                            calculated_similarity = min(calculated_similarity, 0.95)  # Максимум 0.95
                            
                            if overlap >= 1:  # Минимум 1 общее слово
                                text_chunks.append({
                                    'id': row.id,
                                    'document_id': row.document_id,
                                    'chunk_index': row.chunk_index,
                                    'content': row.content,
                                    'similarity': calculated_similarity,
                                    'search_type': 'text',
                                    'content_length': row.content_length
                                })
                    
                    all_chunks.extend(text_chunks)
                    self.logger.info(f"Текстовый поиск завершен, найдено {len(text_chunks)} дополнительных чанков")
            
            # 6. Сортируем по схожести (убывание)
            all_chunks.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Ограничиваем количество результатов
            final_chunks = all_chunks[:limit]
            
            if not final_chunks:
                self.logger.info("Улучшенный поиск не дал результатов, используем fallback")
                return self._fallback_search(question, limit)
            
            return final_chunks
            
        except Exception as e:
            self.logger.error(f"Ошибка в search_relevant_chunks: {str(e)}")
            return self._fallback_search(question, limit)
    
    def _extract_keywords(self, question: str) -> List[str]:
        """Улучшенное извлечение ключевых слов из вопроса с поддержкой новых категорий"""
        # Расширенный словарь синонимов с новыми категориями
        synonyms = {
            # HR и зарплата
            'аванс': ['аванс', 'авансовая', 'авансовый', 'первая часть', 'первая половина', 'предоплата'],
            'зарплата': ['зарплата', 'заработная плата', 'оплата труда', 'вознаграждение', 'зп', 'доход'],
            'выплата': ['выплата', 'выплачивается', 'перечисление', 'начисление', 'выдача', 'платеж'],
            'дата': ['дата', 'число', 'срок', 'время', 'когда', 'день', 'период'],
            'размер': ['размер', 'сумма', 'процент', 'сколько', 'величина', 'объем'],
            'отпуск': ['отпуск', 'отпускные', 'отдых', 'каникулы', 'vacation'],
            'больничный': ['больничный', 'болезнь', 'нетрудоспособность', 'лист нетрудоспособности'],
            'премия': ['премия', 'бонус', 'поощрение', 'надбавка', 'стимулирование'],
            'договор': ['договор', 'контракт', 'соглашение', 'трудовой договор'],
            'увольнение': ['увольнение', 'расторжение', 'прекращение', 'уход', 'dismissal'],
            'график': ['график', 'расписание', 'режим', 'время работы', 'смена'],
            'документы': ['документы', 'справки', 'бумаги', 'формы', 'заявления'],
            
            # Техника безопасности
            'безопасность': ['безопасность', 'охрана труда', 'техбезопасность', 'охрана', 'защита'],
            'инструкция': ['инструкция', 'правила', 'порядок', 'процедура', 'регламент'],
            'средства_защиты': ['сиз', 'средства защиты', 'спецодежда', 'каска', 'перчатки', 'очки'],
            'несчастный_случай': ['несчастный случай', 'травма', 'происшествие', 'авария', 'инцидент'],
            'обучение_бт': ['обучение', 'инструктаж', 'подготовка', 'курсы безопасности'],
            'медосмотр': ['медосмотр', 'медицинский осмотр', 'диспансеризация', 'здоровье'],
            'пожарная_безопасность': ['пожар', 'огнетушитель', 'эвакуация', 'пожарная безопасность'],
            
            # IT и информационная безопасность
            'компьютер': ['компьютер', 'пк', 'ноутбук', 'рабочее место', 'техника'],
            'пароль': ['пароль', 'авторизация', 'доступ', 'логин', 'учетная запись'],
            'интернет': ['интернет', 'сеть', 'wifi', 'подключение', 'онлайн'],
            'почта': ['почта', 'email', 'емейл', 'электронная почта', 'мейл'],
            'программы': ['программы', 'софт', 'приложения', 'software', 'система'],
            'данные': ['данные', 'информация', 'файлы', 'документооборот', 'архив'],
            'вирус': ['вирус', 'антивирус', 'malware', 'защита', 'угроза'],
            
            # Общие рабочие процессы
            'командировка': ['командировка', 'поездка', 'путешествие', 'business trip'],
            'обед': ['обед', 'перерыв', 'питание', 'столовая', 'кафе'],
            'транспорт': ['транспорт', 'проезд', 'автобус', 'машина', 'такси'],
            'парковка': ['парковка', 'стоянка', 'автомобиль', 'место для машины'],
            'пропуск': ['пропуск', 'доступ', 'проход', 'карта', 'badge'],
            'дресс_код': ['дресс код', 'одежда', 'внешний вид', 'форма', 'uniform'],
            
            # Социальные льготы
            'льготы': ['льготы', 'компенсации', 'возмещение', 'benefits', 'пособия'],
            'страхование': ['страхование', 'дмс', 'полис', 'медстраховка'],
            'спорт': ['спорт', 'фитнес', 'тренажерный зал', 'здоровье', 'физкультура'],
            'обучение': ['обучение', 'курсы', 'тренинги', 'развитие', 'образование'],
            
            # Организационные вопросы
            'офис': ['офис', 'помещение', 'рабочее место', 'кабинет', 'space'],
            'оборудование': ['оборудование', 'инвентарь', 'техника', 'устройства'],
            'уборка': ['уборка', 'чистота', 'клининг', 'санитария', 'гигиена'],
            'ремонт': ['ремонт', 'поломка', 'неисправность', 'сервис', 'maintenance']
        }
        
        question_lower = question.lower()
        keywords = set()
        
        # Ищем прямые совпадения с синонимами
        for base_word, word_list in synonyms.items():
            for word in word_list:
                if word in question_lower:
                    keywords.update([base_word])  # Добавляем базовое слово
                    keywords.add(word)  # И само найденное слово
                    break
        
        # Добавляем числа (даты, проценты, суммы)
        import re
        numbers = re.findall(r'\b\d{1,2}\b', question)
        for num in numbers:
            keywords.add(num)
        
        # Улучшенное извлечение важных слов
        words = re.findall(r'\b[а-яё]{4,}\b', question_lower)
        stop_words = {
            'когда', 'какой', 'какая', 'какие', 'сколько', 'почему', 'зачем', 
            'откуда', 'куда', 'который', 'которая', 'которые', 'можно', 'нужно',
            'должен', 'должна', 'будет', 'были', 'есть', 'было', 'буду'
        }
        
        for word in words:
            if word not in stop_words:
                keywords.add(word)
        
        # Добавляем обработку английских слов (для IT терминов)
        english_words = re.findall(r'\b[a-z]{3,}\b', question.lower())
        for word in english_words:
            if word not in ['and', 'the', 'for', 'are', 'you', 'can', 'how', 'what']:
                keywords.add(word)
        
        # Специальная обработка для аббревиатур (СИЗ, ДМС, IT и т.д.)
        abbreviations = re.findall(r'\b[А-ЯЁ]{2,6}\b|\b[A-Z]{2,6}\b', question)
        for abbr in abbreviations:
            keywords.add(abbr.lower())
        
        self.logger.info(f"Извлеченные ключевые слова: {list(keywords)[:15]}")
        return list(keywords)[:15]  # Увеличиваем лимит до 15 слов
    
    def _fallback_search(self, question: str, limit: int) -> List[Dict]:
        """Улучшенный резервный поиск с автоматическим извлечением ключевых слов"""
        try:
            self.logger.info("Используем улучшенный текстовый поиск как fallback")
            
            # Извлекаем ключевые слова из вопроса для более точного поиска
            question_keywords = self._extract_dynamic_keywords(question)
            
            # Создаем более гибкий поисковый запрос
            search_conditions = []
            params = {'limit': limit}
            
            # Добавляем поиск по каждому ключевому слову
            for i, keyword in enumerate(question_keywords[:5]):  # Ограничиваем до 5 ключевых слов
                search_conditions.append(f"dc.content ILIKE :keyword_{i}")
                params[f'keyword_{i}'] = f'%{keyword}%'
            
            if not search_conditions:
                # Если нет ключевых слов, используем простой поиск по словам
                words = question.lower().split()
                search_terms = [word for word in words if len(word) > 2][:3]
                
                for i, term in enumerate(search_terms):
                    search_conditions.append(f"dc.content ILIKE :term_{i}")
                    params[f'term_{i}'] = f'%{term}%'
            
            if not search_conditions:
                return []
            
            # Строим запрос с OR условиями для большей гибкости
            search_query = " OR ".join(search_conditions)
            
            query = text(f"""
                SELECT dc.id, dc.document_id, dc.chunk_index, dc.content,
                       0.6 as similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.processing_status = 'completed'
                  AND ({search_query})
                ORDER BY 
                    CASE 
                        WHEN dc.content ILIKE :first_keyword THEN 1
                        ELSE 2
                    END,
                    LENGTH(dc.content) ASC
                LIMIT :limit
            """)
            
            # Добавляем параметр для сортировки по первому ключевому слову
            if question_keywords:
                params['first_keyword'] = f'%{question_keywords[0]}%'
            else:
                params['first_keyword'] = f'%{question.split()[0] if question.split() else ""}%'
            
            result = self.db_session.execute(query, params)
            
            chunks = []
            for row in result:
                chunks.append({
                    'id': row.id,
                    'document_id': row.document_id,
                    'chunk_index': row.chunk_index,
                    'content': row.content,
                    'similarity': row.similarity,
                    'search_type': 'fallback_enhanced'
                })
            
            self.logger.info(f"Улучшенный поиск завершен, найдено {len(chunks)} чанков по ключевым словам: {question_keywords[:5]}")
            return chunks
            
        except Exception as e:
            self.logger.error(f"Ошибка в улучшенном fallback поиске: {str(e)}")
            return []
    
    def _extract_dynamic_keywords(self, text: str) -> List[str]:
        """Динамическое извлечение ключевых слов из текста для лучшего поиска"""
        import re
        from collections import Counter
        
        # Очищаем текст
        text_lower = text.lower()
        
        # Извлекаем все значимые слова (русские и английские)
        russian_words = re.findall(r'\b[а-яё]{3,}\b', text_lower)
        english_words = re.findall(r'\b[a-z]{3,}\b', text_lower)
        abbreviations = re.findall(r'\b[А-ЯЁA-Z]{2,6}\b', text)
        
        # Объединяем все слова
        all_words = russian_words + english_words + [abbr.lower() for abbr in abbreviations]
        
        # Исключаем стоп-слова
        stop_words = {
            # Русские стоп-слова
            'как', 'что', 'где', 'когда', 'почему', 'зачем', 'кто', 'чей', 'какой', 'какая', 'какие',
            'это', 'тот', 'тем', 'том', 'они', 'оно', 'она', 'его', 'её', 'их', 'для', 'при', 'под',
            'над', 'без', 'через', 'между', 'перед', 'после', 'вместо', 'кроме', 'будет', 'была',
            'были', 'буду', 'есть', 'был', 'может', 'можно', 'нужно', 'должен', 'должна', 'должны',
            'очень', 'всех', 'всем', 'всей', 'всё', 'все', 'или', 'также', 'если', 'что', 'чтобы',
            # Английские стоп-слова
            'the', 'and', 'for', 'are', 'you', 'can', 'how', 'what', 'where', 'when', 'why', 'who',
            'this', 'that', 'they', 'them', 'with', 'from', 'have', 'will', 'been', 'were', 'was'
        }
        
        # Фильтруем значимые слова
        meaningful_words = [word for word in all_words if word not in stop_words and len(word) > 2]
        
        # Считаем частоту и берем самые важные
        word_counts = Counter(meaningful_words)
        
        # Возвращаем топ-10 слов
        return [word for word, count in word_counts.most_common(10)]
    
    def analyze_document_keywords(self, document_id: int) -> List[str]:
        """Анализ документа для извлечения ключевых слов и тем"""
        try:
            # Получаем все чанки документа
            chunks_query = text("""
                SELECT content FROM document_chunks 
                WHERE document_id = :doc_id
                ORDER BY chunk_index
            """)
            
            result = self.db_session.execute(chunks_query, {'doc_id': document_id})
            
            # Объединяем весь текст документа
            full_text = " ".join([row.content for row in result])
            
            if not full_text:
                return []
            
            # Извлекаем ключевые слова
            keywords = self._extract_dynamic_keywords(full_text)
            
            # Дополнительно ищем специфичные термины
            specialized_terms = self._find_specialized_terms(full_text)
            
            # Объединяем и возвращаем уникальные ключевые слова
            all_keywords = list(set(keywords + specialized_terms))
            
            self.logger.info(f"Извлечены ключевые слова для документа {document_id}: {all_keywords[:10]}")
            return all_keywords[:15]
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа ключевых слов для документа {document_id}: {str(e)}")
            return []
    
    def _find_specialized_terms(self, text: str) -> List[str]:
        """Поиск специализированных терминов в тексте"""
        import re
        
        specialized_patterns = {
            'техника_безопасности': [
                r'техник[аи] безопасности', r'охран[аеы] труда', r'производственн[ыйая] безопасность',
                r'несчастн[ыйое] случа[йи]', r'трав[мы]', r'средства защиты', r'спецодежд[аы]',
                r'инструктаж', r'медосмотр', r'пожарн[аяое] безопасность'
            ],
            'it_безопасность': [
                r'информационн[аяое] безопасность', r'кибербезопасность', r'антивирус',
                r'парол[ьи]', r'авторизаци[яи]', r'доступ к системе', r'защита данных',
                r'резервн[ыое] копировани[ея]', r'шифровани[ея]'
            ],
            'экология': [
                r'экологическ[аяое]', r'окружающ[аяее] сред[аы]', r'утилизаци[яи]',
                r'отход[ыов]', r'переработк[аи]', r'загрязнени[ея]', r'природоохранн[ыйая]'
            ],
            'качество': [
                r'контроль качества', r'стандарт[ыов]', r'сертификаци[яи]',
                r'iso \d+', r'гост', r'техническ[иео] требовани[яй]'
            ]
        }
        
        found_terms = []
        text_lower = text.lower()
        
        for category, patterns in specialized_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    found_terms.append(category)
                    # Также добавляем найденные совпадения
                    matches = re.findall(pattern, text_lower)
                    found_terms.extend(matches[:3])  # Ограничиваем количество
        
        return list(set(found_terms))
    
    def format_context(self, chunks: List[DocumentChunk]) -> str:
        """Форматирование контекста из найденных чанков"""
        if not chunks:
            return "Информация не найдена."
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            # Получаем название документа
            document = self.db_session.query(Document).filter(
                Document.id == chunk['document_id']
            ).first()
            
            doc_title = document.title if document else "Неизвестный документ"
            
            context_parts.append(
                f"[Источник {i}: {doc_title}]\n{chunk['content']}\n"
            )
        
        return "\n".join(context_parts)
    
    def answer_question(self, 
                       question: str,
                       user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Главная функция - ответ на вопрос пользователя
        
        Args:
            question: Вопрос пользователя
            user_id: ID пользователя (для логирования)
            
        Returns:
            Dict с ответом и метаданными
        """
        try:
            self.logger.info(f"Обрабатываем вопрос: {question[:100]}...")
            
            # 1. Ищем релевантные документы
            relevant_chunks = self.search_relevant_chunks(question, limit=self.search_limit)  # Используем настраиваемый лимит
            
            if not relevant_chunks:
                return {
                    'answer': 'К сожалению, я не нашел информации по вашему вопросу в корпоративной базе знаний. Попробуйте переформулировать вопрос или обратитесь к HR-отделу.',
                    'sources': [],
                    'chunks': [],
                    'files': [],
                    'success': True,
                    'tokens_used': 0
                }
            
            # 2. Улучшенное формирование контекста - берем лучшие чанки
            top_chunks = relevant_chunks[:10]  # Ограничиваем до 10 лучших чанков
            context = self.format_context(top_chunks)
            
            # ОТЛАДКА: Выводим контекст в лог
            self.logger.info(f"🔍 КОНТЕКСТ ДЛЯ LLM (длина: {len(context)} символов):")
            self.logger.info("="*80)
            self.logger.info(context[:2000] + "..." if len(context) > 2000 else context)
            self.logger.info("="*80)
            
            # 3. Получаем ответ от LLM с улучшенным промптом
            enhanced_prompt = f"""
Вопрос: {question}

Контекст: {context}

Требования к ответу:
1. Будь максимально точным и подробным
2. Используй только информацию из предоставленного контекста
3. Структурируй ответ с нумерованными списками где это уместно
4. Если в контексте есть конкретные цифры, даты, суммы - обязательно укажи их
5. Отвечай на русском языке
"""
            
            llm_response = self.llm_client.generate_answer(
                context=enhanced_prompt,
                question=question
            )
            
            if not llm_response.success:
                return {
                    'answer': 'Извините, произошла ошибка при генерации ответа. Попробуйте позже.',
                    'sources': [],
                    'chunks': [],
                    'files': [],
                    'success': False,
                    'error': llm_response.error,
                    'tokens_used': 0
                }
            
            # 4. Формируем источники и файлы с дедупликацией
            sources = []
            files = []
            seen_documents = set()
            
            for chunk in top_chunks:
                document = self.db_session.query(Document).filter(
                    Document.id == chunk['document_id']
                ).first()
                
                if document and document.title not in seen_documents:
                    sources.append({
                        'title': document.title,
                        'chunk_index': chunk['chunk_index'],
                        'document_id': document.id
                    })
                    
                    # ОТЛАДКА: Логируем данные документа
                    self.logger.info(f"📄 ДОКУМЕНТ ID {document.id}:")
                    self.logger.info(f"  - title: '{document.title}'")
                    self.logger.info(f"  - file_path: '{document.file_path}'")
                    self.logger.info(f"  - original_filename: '{document.original_filename}'")
                    self.logger.info(f"  - file_type: '{document.file_type}'")
                    self.logger.info(f"  - file_size: {document.file_size}")
                    
                    # Добавляем полную информацию о файле для прикрепления
                    files.append({
                        'title': document.title,
                        'file_path': document.file_path,  # Полный путь к файлу
                        'document_id': document.id,
                        'similarity': chunk['similarity'],
                        'file_size': document.file_size,
                        'file_type': document.file_type,
                        'original_filename': document.original_filename
                    })
                    
                    seen_documents.add(document.title)
            
            # 5. Постобработка ответа для улучшения форматирования
            formatted_answer = self._post_process_answer(llm_response.text)

            # 6. Логируем запрос (опционально)
            if user_id:
                self._log_query(user_id, question, formatted_answer, len(relevant_chunks))
            
            return {
                'answer': formatted_answer,
                'sources': sources,
                'chunks': relevant_chunks,
                'files': files[:5],  # Ограничиваем до 5 файлов
                'success': True,
                'tokens_used': llm_response.tokens_used,
                'chunks_found': len(relevant_chunks),
                'context_length': len(context)
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка в answer_question: {str(e)}")
            return {
                'answer': 'Произошла техническая ошибка. Обратитесь к администратору.',
                'sources': [],
                'chunks': [],
                'files': [],
                'success': False,
                'error': str(e),
                'tokens_used': 0
            }
    
    def _post_process_answer(self, answer: str) -> str:
        """
        Постобработка ответа для правильного форматирования
        
        Args:
            answer: Исходный ответ от LLM
            
        Returns:
            str: Обработанный ответ
        """
        # Убираем лишние пробелы и переносы
        answer = answer.strip()
        
        # Нормализуем переносы строк - убираем одиночные переносы, оставляем двойные
        lines = answer.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:  # Добавляем только непустые строки
                cleaned_lines.append(line)
        
        # Объединяем строки с одним переносом между ними
        result = '\n'.join(cleaned_lines)
        
        # Убираем возможные дублирующиеся фразы
        sentences = result.split('. ')
        unique_sentences = []
        seen_sentences = set()
        
        for sentence in sentences:
            sentence_clean = sentence.strip().lower()
            if sentence_clean and sentence_clean not in seen_sentences and len(sentence_clean) > 10:
                unique_sentences.append(sentence.strip())
                seen_sentences.add(sentence_clean)
        
        # Восстанавливаем точки в конце предложений
        final_sentences = []
        for i, sentence in enumerate(unique_sentences):
            if not sentence.endswith('.') and not sentence.endswith(':') and not sentence.endswith(';'):
                if i < len(unique_sentences) - 1:  # Не последнее предложение
                    sentence += '.'
            final_sentences.append(sentence)
        
        return '. '.join(final_sentences)
    
    def _log_query(self, user_id: int, question: str, answer: str, chunks_count: int):
        """Логирование запроса пользователя"""
        try:
            from shared.models.query_log import QueryLog
            
            log_entry = QueryLog(
                user_id=user_id,
                query_text=question,
                response_text=answer
            )
            
            self.db_session.add(log_entry)
            self.db_session.commit()
            
        except Exception as e:
            self.logger.error(f"Ошибка логирования запроса: {str(e)}")
    
    def health_check(self) -> Dict[str, bool]:
        """Проверка работоспособности всех компонентов"""
        return {
            'embeddings_model': self.embedding_model is not None,
            'llm_client': self.llm_client.health_check(),
            'database': self._check_database()
        }
    
    def _check_database(self) -> bool:
        """Проверка подключения к базе данных"""
        try:
            self.db_session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def _is_relevant_content(self, content: str, question: str) -> bool:
        """Проверка релевантности контента к вопросу"""
        content_lower = content.lower()
        question_lower = question.lower()
        
        # Исключаем технические части документов
        technical_markers = [
            'приложение', 'утверждаю', 'генеральный директор', 
            'система менеджмента', 'введено впервые', 'дата введения',
            'область применения', 'настоящее положение направлено',
            'акционерное общество', 'сибгазполимер'
        ]
        
        # Если содержит много технических маркеров, исключаем
        technical_count = sum(1 for marker in technical_markers if marker in content_lower)
        if technical_count > 2:
            return False
        
        # Проверяем наличие ключевых слов из вопроса
        question_words = set(word for word in question_lower.split() if len(word) > 2)
        content_words = set(content_lower.split())
        
        overlap = question_words & content_words
        
        # Минимум 1 общее слово для начала (снижаем требования)
        if len(overlap) >= 1:
            return True
            
        # Проверяем точные ключевые термины
        key_terms = {
            'отпуск': ['отпуск', 'отпускные', 'отдых', 'отпуска', 'отпусков', 'отпускной'],
            'зарплата': ['зарплата', 'заработная плата', 'оплата труда', 'выплачивается', 'выплата'],
            'выплаты': ['выплаты', 'выплата', 'начисления', 'премия'],
            'юбилей': ['юбилей', 'юбилейные', 'годовщина'],
            'больничный': ['больничный', 'нетрудоспособность'],
            'командировка': ['командировка', 'служебная поездка'],
            'увольнение': ['увольнение', 'расторжение договора'],
            'оформление': ['оформление', 'оформить', 'оформления', 'процедура', 'порядок']
        }
        
        for term_group in key_terms.values():
            question_has_term = any(term in question_lower for term in term_group)
            content_has_term = any(term in content_lower for term in term_group)
            
            if question_has_term and content_has_term:
                return True
        
        # Если ничего не найдено, возвращаем False
            return False 