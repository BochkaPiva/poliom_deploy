"""
Модели меню (разделы и элементы)
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base


class MenuSection(Base):
    __tablename__ = 'menu_sections'
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    order_index = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Связи
    items = relationship("MenuItem", back_populates="section", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MenuSection(id={self.id}, title='{self.title}', order={self.order_index})>"


class MenuItem(Base):
    __tablename__ = 'menu_items'
    
    id = Column(Integer, primary_key=True, index=True)
    section_id = Column(Integer, ForeignKey('menu_sections.id'), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    content = Column(Text, nullable=False)
    order_index = Column(Integer, default=0, nullable=False, index=True)
    source_document_ids = Column(Text, nullable=True)  # JSON список ID документов-источников
    source_document_names = Column(Text, nullable=True)  # JSON список названий документов
    source_chunk_ids = Column(Text, nullable=True)  # JSON список ID чанков-источников
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Связи
    section = relationship("MenuSection", back_populates="items")
    
    def __repr__(self):
        return f"<MenuItem(id={self.id}, title='{self.title}', section_id={self.section_id})>" 