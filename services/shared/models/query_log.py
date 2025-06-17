"""
Модель логирования запросов пользователей
"""

from sqlalchemy import Column, Integer, Text, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base


class QueryLog(Base):
    __tablename__ = 'query_logs'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=True)
    response_time = Column(Float, nullable=True, index=True)
    similarity_score = Column(Float, nullable=True, index=True)
    documents_used = Column(Text, nullable=True)  # JSON список использованных документов
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Связь с пользователем
    user = relationship("User", back_populates="query_logs")
    
    def __repr__(self):
        return f"<QueryLog(id={self.id}, user_id={self.user_id}, query='{self.query[:50]}...')>" 