"""
Admin Panel
Веб-интерфейс для управления корпоративным чат-ботом
"""

import os
import sys
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# Загружаем переменные окружения из .env.local
from dotenv import load_dotenv
load_dotenv('.env.local')

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session
from sqlalchemy import desc, func, text

# Добавляем путь к shared модулям для локального запуска
current_dir = Path(__file__).parent
shared_path = current_dir.parent / "shared"
if shared_path.exists():
    sys.path.insert(0, str(shared_path))

# Импортируем shared модули
try:
    # Пробуем импорт для Docker
    from shared.models.database import SessionLocal, engine, Base
    from shared.models import Document, DocumentChunk, Admin, User
    from shared.models.query_log import QueryLog
    from shared.models.menu import MenuSection, MenuItem
    from shared.utils.auth import get_password_hash, verify_password
except ImportError:
    # Если не получилось, пробуем локальный импорт
    from models.database import SessionLocal, engine, Base
    from models import Document, DocumentChunk, Admin, User
    from models.query_log import QueryLog
    from models.menu import MenuSection, MenuItem
    from utils.auth import get_password_hash, verify_password

# Импортируем Celery для обработки документов
try:
    from celery.result import AsyncResult
    import os
    
    # Принудительно устанавливаем переменные окружения для Celery
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    os.environ["CELERY_BROKER_URL"] = redis_url
    os.environ["CELERY_RESULT_BACKEND"] = redis_url
    
    # Теперь импортируем celery_app с правильными переменными окружения
    from celery_app import app as celery_app
    # И затем импортируем задачи
    from tasks import process_document
    CELERY_AVAILABLE = True
    
except ImportError:
    print("⚠️  Celery недоступен - функции обработки документов отключены")
    CELERY_AVAILABLE = False
    AsyncResult = None
    celery_app = None
    process_document = None

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаем FastAPI приложение
app = FastAPI(
    title="Admin Panel",
    description="Панель администратора корпоративного чат-бота",
    version="1.0.0"
)

# Секретный ключ для сессий
SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "super-secret-admin-key-change-in-production")

# Обработчик исключений для редиректа на страницу входа
@app.exception_handler(401)
async def auth_exception_handler(request: Request, exc: HTTPException):
    return RedirectResponse(url="/login")

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    # Создаем таблицы
    Base.metadata.create_all(bind=engine)
    logger.info("База данных инициализирована")
    
    # Создаем администратора по умолчанию, если его нет
    db = SessionLocal()
    try:
        admin_count = db.query(Admin).count()
        if admin_count == 0:
            default_admin = Admin(
                username="admin",
                email="admin@example.com",
                hashed_password=get_password_hash("admin123"),
                full_name="Администратор по умолчанию",
                is_active=True
            )
            db.add(default_admin)
            db.commit()
            logger.info("Создан администратор по умолчанию: admin/admin123")
    except Exception as e:
        logger.error(f"Ошибка создания администратора по умолчанию: {e}")
    finally:
        db.close()

# Настройка статических файлов и шаблонов
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

# Определяем папку uploads в зависимости от окружения
if os.getenv("DOCKER_ENV"):
    uploads_dir = Path("/app/uploads")
else:
    uploads_dir = Path(__file__).parent / "uploads"

static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)
uploads_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# Настройки загрузки файлов
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_admin(request: Request, db: Session = Depends(get_db)) -> Optional[Admin]:
    """Получение текущего авторизованного администратора"""
    admin_id = request.cookies.get("admin_id")
    admin_token = request.cookies.get("admin_token")
    
    if not admin_id or not admin_token:
        return None
    
    try:
        admin = db.query(Admin).filter(Admin.id == int(admin_id), Admin.is_active == True).first()
        if admin and admin_token == f"{admin.id}_{admin.username}_{SECRET_KEY}":
            return admin
    except:
        pass
    
    return None


def require_auth(request: Request, db: Session = Depends(get_db)):
    """Проверка авторизации (dependency)"""
    admin = get_current_admin(request, db)
    if not admin:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return admin


def validate_file(file: UploadFile) -> None:
    """Валидация загружаемого файла"""
    # Проверяем расширение
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый тип файла. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Проверяем размер (приблизительно)
    if hasattr(file, 'size') and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой. Максимальный размер: {MAX_FILE_SIZE // (1024*1024)}MB"
        )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Обработка входа"""
    try:
        admin = db.query(Admin).filter(Admin.username == username, Admin.is_active == True).first()
        
        if not admin or not verify_password(password, admin.hashed_password):
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Неверное имя пользователя или пароль"
            })
        
        # Обновляем время последнего входа
        try:
            admin.last_login = func.now()
            db.commit()
            logger.info(f"Обновлено время последнего входа для администратора: {admin.username}")
        except Exception as e:
            logger.warning(f"Не удалось обновить last_login для {admin.username}: {e}")
            # Не прерываем процесс входа из-за этой ошибки
        
        # Создаем токен авторизации
        token = f"{admin.id}_{admin.username}_{SECRET_KEY}"
        
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("admin_id", str(admin.id), max_age=86400)  # 24 часа
        response.set_cookie("admin_token", token, max_age=86400)
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка входа: {str(e)}")
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Ошибка входа"
        })


@app.post("/logout")
async def logout():
    """Выход"""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("admin_id")
    response.delete_cookie("admin_token")
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Главная страница админ-панели"""
    try:
        # Получаем статистику
        total_documents = db.query(Document).count()
        completed_documents = db.query(Document).filter(Document.processing_status == "completed").count()
        failed_documents = db.query(Document).filter(Document.processing_status == "failed").count()
        total_users = db.query(User).count()
        total_admins = db.query(Admin).count()
        
        # Последние документы
        recent_documents = db.query(Document).order_by(Document.created_at.desc()).limit(5).all()
        
        # Последние запросы пользователей
        recent_queries = db.query(QueryLog).order_by(QueryLog.created_at.desc()).limit(10).all()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "admin": admin,
            "total_documents": total_documents,
            "completed_documents": completed_documents,
            "failed_documents": failed_documents,
            "total_users": total_users,
            "total_admins": total_admins,
            "recent_documents": recent_documents,
            "recent_queries": recent_queries
        })
        
    except Exception as e:
        logger.error(f"Ошибка загрузки дашборда: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка загрузки дашборда"
        })


@app.get("/documents", response_class=HTMLResponse)
async def documents_page(request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Страница управления документами"""
    try:
        # Получаем все документы
        documents = db.query(Document).order_by(Document.created_at.desc()).all()
        
        return templates.TemplateResponse("documents.html", {
            "request": request,
            "admin": admin,
            "documents": documents
        })
        
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы документов: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка загрузки документов"
        })


@app.post("/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Загрузка документа через веб-форму"""
    try:
        logger.info(f"Начинаю загрузку документа: {file.filename}, title: {title}, admin: {admin.username}")
        
        # Валидируем файл
        validate_file(file)
        logger.info("Файл прошел валидацию")
        
        # Генерируем уникальное имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = Path(file.filename).suffix.lower()
        unique_filename = f"{timestamp}_{file.filename}"
        file_path = uploads_dir / unique_filename
        logger.info(f"Сохраняю файл как: {file_path}")
        
        # Сохраняем файл
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("Файл сохранен на диск")
        
        # Получаем размер файла
        file_size = file_path.stat().st_size
        logger.info(f"Размер файла: {file_size} байт")
        
        # Создаем запись в базе данных
        # ВАЖНО: сохраняем путь как относительный к /app/uploads для надежности
        relative_file_path = f"/app/uploads/{unique_filename}"
        document = Document(
            filename=unique_filename,
            original_filename=file.filename,
            file_path=relative_file_path,  # Используем стандартизированный путь
            file_size=file_size,
            file_type=file_ext.lstrip('.'),
            title=title or file.filename,
            description="",  # Устанавливаем пустое описание
            processing_status="pending",
            uploaded_by=admin.id  # Используем ID текущего авторизованного администратора
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        logger.info(f"Документ сохранен в БД с ID: {document.id}, загрузчик: {admin.username}")
        
        # Запускаем задачу обработки через Celery
        if CELERY_AVAILABLE and process_document:
            try:
                task = process_document.delay(document.id)
                logger.info(f"Документ {document.id} загружен и отправлен на обработку. Task ID: {task.id}")
            except Exception as celery_error:
                logger.error(f"Ошибка запуска Celery задачи: {str(celery_error)}")
                # Не прерываем процесс, просто помечаем как загруженный
                document.processing_status = "uploaded"
                db.commit()
        else:
            # Если Celery недоступен, просто помечаем как загруженный
            document.processing_status = "uploaded"
            db.commit()
            logger.info(f"Документ {document.id} загружен (Celery недоступен)")
        
        logger.info("Загрузка документа завершена успешно")
        return RedirectResponse(url="/documents?success=uploaded", status_code=303)
                
    except HTTPException as e:
        logger.error(f"HTTP ошибка при загрузке документа: {e.detail}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": e.detail
        })
    except Exception as e:
        logger.error(f"Неожиданная ошибка загрузки документа: {str(e)}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        import traceback
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Ошибка загрузки документа: {str(e)}"
        })


@app.post("/documents/{document_id}/delete")
async def delete_document(document_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Удаление документа"""
    try:
        # Получаем только основную информацию о документе без связанных объектов
        document_info = db.execute(
            text("SELECT id, title, original_filename, file_path, processing_status FROM documents WHERE id = :doc_id"),
            {"doc_id": document_id}
        ).fetchone()
        
        if not document_info:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Документ не найден"
            })
        
        doc_id, title, original_filename, file_path, status = document_info
        
        logger.info(f"Начинаю удаление документа {doc_id}: {title}")
        
        # 1. Удаляем чанки напрямую через SQL (избегаем проблем с эмбеддингами)
        try:
            chunks_result = db.execute(text("DELETE FROM document_chunks WHERE document_id = :doc_id"), {"doc_id": document_id})
            deleted_chunks = chunks_result.rowcount
            logger.info(f"Удалено чанков: {deleted_chunks}")
        except Exception as e:
            logger.warning(f"Ошибка удаления чанков документа {document_id}: {str(e)}")
        
        # 2. Удаляем файл с диска
        try:
            file_path_obj = Path(file_path)
            if file_path_obj.exists():
                file_path_obj.unlink()
                logger.info(f"Файл {file_path} удален с диска")
            else:
                logger.warning(f"Файл не найден: {file_path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить файл {file_path}: {str(e)}")
        
        # 3. Удаляем документ напрямую через SQL
        try:
            doc_result = db.execute(text("DELETE FROM documents WHERE id = :doc_id"), {"doc_id": document_id})
            if doc_result.rowcount > 0:
                db.commit()
                logger.info(f"Документ {document_id} успешно удален")
                return RedirectResponse(url="/documents?success=deleted", status_code=303)
            else:
                logger.error(f"Не удалось удалить документ {document_id} из базы данных")
                return templates.TemplateResponse("error.html", {
                    "request": request,
                    "error": "Ошибка удаления документа из базы данных"
                })
        except Exception as e:
            logger.error(f"Ошибка удаления документа {document_id} из БД: {str(e)}")
            db.rollback()
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Ошибка удаления документа из базы данных"
            })
                
    except Exception as e:
        logger.error(f"Ошибка удаления документа {document_id}: {str(e)}")
        db.rollback()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка удаления документа"
        })


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Страница управления пользователями"""
    try:
        # Получаем всех пользователей
        users = db.query(User).order_by(User.created_at.desc()).all()
        
        # Получаем статистику по пользователям
        for user in users:
            user.queries_count = db.query(QueryLog).filter(QueryLog.user_id == user.id).count()
            last_query = db.query(QueryLog).filter(QueryLog.user_id == user.id).order_by(QueryLog.created_at.desc()).first()
            user.last_query_date = last_query.created_at if last_query else None
        
        return templates.TemplateResponse("users.html", {
            "request": request,
            "admin": admin,
            "users": users
        })
        
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы пользователей: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка загрузки пользователей"
        })


@app.post("/users/create")
async def create_user(
    request: Request,
    telegram_id: int = Form(...),
    username: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Создание нового пользователя"""
    try:
        # Проверяем уникальность telegram_id
        existing_user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if existing_user:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Пользователь с таким Telegram ID уже существует"
            })
        
        # Создаем нового пользователя
        new_user = User(
            telegram_id=telegram_id,
            username=username or None,
            first_name=first_name or None,
            last_name=last_name or None,
            is_active=True
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        logger.info(f"Администратор {admin.username} создал пользователя с Telegram ID: {telegram_id}")
        
        return RedirectResponse(url="/users?success=created", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка создания пользователя: {str(e)}")
        db.rollback()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка создания пользователя"
        })


@app.post("/users/{user_id}/delete")
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Удаление пользователя"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Пользователь не найден"
            })
        
        user_info = f"{user.telegram_id} ({user.first_name or ''} {user.last_name or ''})"
        
        # Сначала удаляем все связанные записи из query_logs
        try:
            deleted_logs = db.execute(
                text("DELETE FROM query_logs WHERE user_id = :user_id"),
                {"user_id": user_id}
            ).rowcount
            logger.info(f"Удалено {deleted_logs} записей логов для пользователя {user_id}")
        except Exception as e:
            logger.warning(f"Ошибка удаления логов пользователя {user_id}: {str(e)}")
        
        # Теперь удаляем пользователя
        db.delete(user)
        db.commit()
        
        logger.info(f"Администратор {admin.username} удалил пользователя {user_id}: {user_info}")
        
        return RedirectResponse(url="/users?success=deleted", status_code=303)
                
    except Exception as e:
        logger.error(f"Ошибка удаления пользователя {user_id}: {str(e)}")
        db.rollback()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка удаления пользователя"
        })


@app.post("/users/{user_id}/block")
async def block_user(user_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Блокировка пользователя"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Пользователь не найден"
            })
        
        user.is_active = False
        db.commit()
        
        return RedirectResponse(url="/users?success=blocked", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка блокировки пользователя {user_id}: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка блокировки пользователя"
        })


@app.post("/users/{user_id}/unblock")
async def unblock_user(user_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Разблокировка пользователя"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Пользователь не найден"
            })
        
        user.is_active = True
        db.commit()
        
        return RedirectResponse(url="/users?success=unblocked", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка разблокировки пользователя {user_id}: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка разблокировки пользователя"
        })


@app.get("/admins", response_class=HTMLResponse)
async def admins_page(request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Страница управления администраторами"""
    try:
        # Получаем всех администраторов
        admins = db.query(Admin).order_by(Admin.created_at.desc()).all()
        
        return templates.TemplateResponse("admins.html", {
            "request": request,
            "admin": admin,
            "admins": admins,
            "current_admin_id": admin.id
        })
        
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы администраторов: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка загрузки администраторов"
        })


@app.post("/admins/create")
async def create_admin(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Создание нового администратора"""
    try:
        # Проверяем уникальность username и email
        existing_admin = db.query(Admin).filter(
            (Admin.username == username) | (Admin.email == email)
        ).first()
        
        if existing_admin:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Администратор с таким именем или email уже существует"
            })
        
        # Создаем нового администратора
        hashed_password = get_password_hash(password)
        new_admin = Admin(
            username=username,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=True
        )
        
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        
        logger.info(f"Создан новый администратор: {username}")
        
        return RedirectResponse(url="/admins?success=created", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка создания администратора: {str(e)}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Ошибка создания администратора: {str(e)}"
        })


@app.post("/admins/{admin_id}/deactivate")
async def deactivate_admin(admin_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Деактивация администратора"""
    try:
        target_admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if not target_admin:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Администратор не найден"
            })
        
        # Нельзя деактивировать самого себя
        if target_admin.id == admin.id:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Нельзя деактивировать самого себя"
            })
        
        target_admin.is_active = False
        db.commit()
        
        return RedirectResponse(url="/admins?success=deactivated", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка деактивации администратора {admin_id}: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка деактивации администратора"
        })


@app.post("/admins/{admin_id}/activate")
async def activate_admin(admin_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Активация администратора"""
    try:
        target_admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if not target_admin:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Администратор не найден"
            })
        
        target_admin.is_active = True
        db.commit()
        
        logger.info(f"Администратор {target_admin.username} активирован пользователем {admin.username}")
        
        return RedirectResponse(url="/admins?success=activated", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка активации администратора {admin_id}: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка активации администратора"
        })


@app.post("/admins/{admin_id}/delete")
async def delete_admin(admin_id: int, request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Удаление администратора"""
    try:
        target_admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if not target_admin:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Администратор не найден"
            })
        
        # Нельзя удалить самого себя
        if target_admin.id == admin.id:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Нельзя удалить самого себя"
            })
        
        # Проверяем, что это не последний активный администратор
        active_admins_count = db.query(Admin).filter(Admin.is_active == True).count()
        if active_admins_count <= 1 and target_admin.is_active:
            return templates.TemplateResponse("error.html", {
                "request": request,
                "error": "Нельзя удалить последнего активного администратора"
            })
        
        username = target_admin.username
        admin_info = f"{username} ({target_admin.email})"
        
        # Проверяем, есть ли документы, загруженные этим администратором
        documents_count = db.query(Document).filter(Document.uploaded_by == admin_id).count()
        
        if documents_count > 0:
            # Переназначаем документы на текущего администратора (того, кто удаляет)
            try:
                updated_docs = db.execute(
                    text("UPDATE documents SET uploaded_by = :new_admin_id WHERE uploaded_by = :old_admin_id"),
                    {"new_admin_id": admin.id, "old_admin_id": admin_id}
                ).rowcount
                logger.info(f"Переназначено {updated_docs} документов с администратора {admin_id} на {admin.id}")
            except Exception as e:
                logger.warning(f"Ошибка переназначения документов администратора {admin_id}: {str(e)}")
                # Если не удается переназначить, устанавливаем NULL
                try:
                    updated_docs = db.execute(
                        text("UPDATE documents SET uploaded_by = NULL WHERE uploaded_by = :admin_id"),
                        {"admin_id": admin_id}
                    ).rowcount
                    logger.info(f"Установлено NULL для {updated_docs} документов администратора {admin_id}")
                except Exception as e2:
                    logger.error(f"Не удалось обновить документы администратора {admin_id}: {str(e2)}")
                    db.rollback()
                    return templates.TemplateResponse("error.html", {
                        "request": request,
                        "error": "Не удалось переназначить документы администратора"
                    })
        
        # Теперь удаляем администратора
        db.delete(target_admin)
        db.commit()
        
        logger.info(f"Администратор {admin.username} удалил администратора {admin_id}: {admin_info}")
        
        return RedirectResponse(url="/admins?success=deleted", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка удаления администратора {admin_id}: {str(e)}")
        db.rollback()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка удаления администратора"
        })


@app.get("/api/documents/status/{document_id}")
async def get_document_status_api(document_id: int, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """API для получения статуса документа"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"error": "Документ не найден"}
        
        return {
            "document_id": document.id,
            "status": document.processing_status,
            "error_message": document.error_message,
            "updated_at": document.updated_at.isoformat() if document.updated_at else None
        }
                
    except Exception as e:
        logger.error(f"Ошибка получения статуса документа {document_id}: {str(e)}")
        return {"error": "Ошибка получения статуса"}


@app.get("/documents/{document_id}/download")
async def download_document(
    document_id: int, 
    db: Session = Depends(get_db), 
    admin: Admin = Depends(require_auth)
):
    """Скачивание документа"""
    try:
        # Получаем документ из базы данных
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Документ не найден")
        
        # Проверяем существование файла
        file_path = Path(document.file_path)
        if not file_path.exists():
            # Пробуем найти файл в uploads директории
            uploads_file_path = uploads_dir / document.original_filename
            if uploads_file_path.exists():
                file_path = uploads_file_path
            else:
                raise HTTPException(status_code=404, detail="Файл документа не найден на диске")
        
        # Определяем MIME тип на основе расширения файла
        file_extension = file_path.suffix.lower()
        media_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain'
        }
        
        media_type = media_types.get(file_extension, 'application/octet-stream')
        
        # Формируем имя файла для скачивания
        safe_filename = document.original_filename or f"document_{document.id}{file_extension}"
        
        logger.info(f"Администратор {admin.username} скачивает документ {document.id}: {safe_filename}")
        
        # Кодируем имя файла для заголовка Content-Disposition
        import urllib.parse
        encoded_filename = urllib.parse.quote(safe_filename, safe='')
        
        # Возвращаем файл для скачивания
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=safe_filename,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Cache-Control": "no-cache"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка скачивания документа {document_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при скачивании файла")


# =================
# FAQ ROUTES
# =================

@app.get("/faq", response_class=HTMLResponse)
async def faq_page(request: Request, db: Session = Depends(get_db), admin: Admin = Depends(require_auth)):
    """Страница управления FAQ"""
    try:
        # Получаем все разделы с вопросами, упорядоченные по order_index
        sections = db.query(MenuSection).order_by(MenuSection.order_index).all()
        
        # Для каждого раздела получаем вопросы, упорядоченные по order_index
        for section in sections:
            section.items = db.query(MenuItem).filter(MenuItem.section_id == section.id).order_by(MenuItem.order_index).all()
        
        # Подсчитываем статистику
        total_sections = db.query(MenuSection).count()
        total_questions = db.query(MenuItem).count()
        
        return templates.TemplateResponse("faq.html", {
            "request": request,
            "admin": admin,
            "sections": sections,
            "total_sections": total_sections,
            "total_questions": total_questions
        })
        
    except Exception as e:
        logger.error(f"Ошибка загрузки страницы FAQ: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Ошибка загрузки FAQ"
        })


@app.post("/faq/sections")
async def create_section(
    request: Request,
    title: str = Form(...),
    order_index: int = Form(10),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Создание нового раздела FAQ"""
    try:
        section = MenuSection(
            title=title,
            order_index=order_index
        )
        
        db.add(section)
        db.commit()
        db.refresh(section)
        
        logger.info(f"Администратор {admin.username} создал раздел FAQ: {title}")
        return RedirectResponse(url="/faq?success=section_created", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка создания раздела FAQ: {str(e)}")
        return RedirectResponse(url="/faq?error=create_failed", status_code=303)


@app.post("/faq/sections/{section_id}")
async def update_section(
    section_id: int,
    request: Request,
    title: str = Form(...),
    order_index: int = Form(10),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Обновление раздела FAQ"""
    try:
        section = db.query(MenuSection).filter(MenuSection.id == section_id).first()
        if not section:
            return RedirectResponse(url="/faq?error=section_not_found", status_code=303)
        
        section.title = title
        section.order_index = order_index
        
        db.commit()
        
        logger.info(f"Администратор {admin.username} обновил раздел FAQ: {title}")
        return RedirectResponse(url="/faq?success=section_updated", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка обновления раздела FAQ: {str(e)}")
        return RedirectResponse(url="/faq?error=update_failed", status_code=303)


@app.post("/faq/sections/{section_id}/delete")
async def delete_section(
    section_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Удаление раздела FAQ"""
    try:
        section = db.query(MenuSection).filter(MenuSection.id == section_id).first()
        if not section:
            return RedirectResponse(url="/faq?error=section_not_found", status_code=303)
        
        section_title = section.title
        
        # Удаляем раздел (вопросы удалятся автоматически благодаря cascade)
        db.delete(section)
        db.commit()
        
        logger.info(f"Администратор {admin.username} удалил раздел FAQ: {section_title}")
        return RedirectResponse(url="/faq?success=section_deleted", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка удаления раздела FAQ: {str(e)}")
        return RedirectResponse(url="/faq?error=delete_failed", status_code=303)


@app.post("/faq/items")
async def create_item(
    request: Request,
    section_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    order_index: int = Form(10),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Создание нового вопроса FAQ"""
    try:
        # Проверяем существование раздела
        section = db.query(MenuSection).filter(MenuSection.id == section_id).first()
        if not section:
            return RedirectResponse(url="/faq?error=section_not_found", status_code=303)
        
        item = MenuItem(
            section_id=section_id,
            title=title,
            content=content,
            order_index=order_index
        )
        
        db.add(item)
        db.commit()
        db.refresh(item)
        
        logger.info(f"Администратор {admin.username} создал вопрос FAQ: {title}")
        return RedirectResponse(url="/faq?success=item_created", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка создания вопроса FAQ: {str(e)}")
        return RedirectResponse(url="/faq?error=create_failed", status_code=303)


@app.post("/faq/items/{item_id}")
async def update_item(
    item_id: int,
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    order_index: int = Form(10),
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Обновление вопроса FAQ"""
    try:
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if not item:
            return RedirectResponse(url="/faq?error=item_not_found", status_code=303)
        
        item.title = title
        item.content = content
        item.order_index = order_index
        
        db.commit()
        
        logger.info(f"Администратор {admin.username} обновил вопрос FAQ: {title}")
        return RedirectResponse(url="/faq?success=item_updated", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка обновления вопроса FAQ: {str(e)}")
        return RedirectResponse(url="/faq?error=update_failed", status_code=303)


@app.post("/faq/items/{item_id}/delete")
async def delete_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_auth)
):
    """Удаление вопроса FAQ"""
    try:
        item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
        if not item:
            return RedirectResponse(url="/faq?error=item_not_found", status_code=303)
        
        item_title = item.title
        
        # Удаляем вопрос
        db.delete(item)
        db.commit()
        
        logger.info(f"Администратор {admin.username} удалил вопрос FAQ: {item_title}")
        return RedirectResponse(url="/faq?success=item_deleted", status_code=303)
        
    except Exception as e:
        logger.error(f"Ошибка удаления вопроса FAQ: {str(e)}")
        return RedirectResponse(url="/faq?error=delete_failed", status_code=303)


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint для проверки готовности системы"""
    try:
        # Проверяем подключение к базе данных
        db.execute(text("SELECT 1"))
        
        # Проверяем наличие расширения pgvector
        result = db.execute(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"))
        has_vector = result.scalar()
        
        if not has_vector:
            raise HTTPException(status_code=503, detail="pgvector extension not available")
        
        # Проверяем возможность работы с векторами
        db.execute(text("SELECT vector_dims(ARRAY[1,2,3]::vector)"))
        
        return {
            "status": "healthy",
            "database": "connected",
            "pgvector": "available",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 