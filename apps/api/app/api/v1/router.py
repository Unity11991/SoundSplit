from fastapi import APIRouter

from app.api.v1.endpoints import uploads, separations, projects, stems, health, storage

api_router = APIRouter()

api_router.include_router(uploads.router, tags=["Uploads"])
api_router.include_router(separations.router, tags=["Separations"])
api_router.include_router(projects.router, tags=["Projects"])
api_router.include_router(stems.router, tags=["Stems"])
api_router.include_router(storage.router, tags=["Storage Management"])
api_router.include_router(health.router, tags=["Health & Readiness"])
