# API router registration
from app.api.health import router as health_router
from app.api.documents import router as documents_router
from app.api.chat import router as chat_router
from app.api.admin import router as admin_router

__all__ = ["health_router", "documents_router", "chat_router", "admin_router"]
