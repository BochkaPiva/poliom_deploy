"""
Модели базы данных для POLIOM HR Assistant
"""

from .database import Base, engine, SessionLocal, get_db
from .user import User
from .admin import Admin
from .document import Document, DocumentChunk
from .query_log import QueryLog
from .menu import MenuSection, MenuItem

__all__ = [
    'Base', 'engine', 'SessionLocal', 'get_db',
    'User', 'Admin', 'Document', 'DocumentChunk', 
    'QueryLog', 'MenuSection', 'MenuItem'
]

# Database models for POLIOM HR Assistant 