import sys
sys.path.insert(0, '/app')

from tasks import process_document
from shared.models import Document
from shared.models.database import engine
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

try:
    docs = db.query(Document).filter(Document.processing_status == 'pending').all()
    print(f'Найдено {len(docs)} документов для обработки')
    
    for doc in docs:
        print(f'Запускаем обработку документа {doc.id}: {doc.original_filename}')
        process_document.delay(doc.id)
    
    print('Все документы отправлены в обработку')
    
finally:
    db.close() 