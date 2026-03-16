from fastapi import APIRouter
from app.api.v1.endpoints import auth, sessions, attendance, qr, courses, admin

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(sessions.router)
router.include_router(attendance.router)
router.include_router(qr.router)
router.include_router(courses.router)
router.include_router(admin.router)
