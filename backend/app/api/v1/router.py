from fastapi import APIRouter
from app.api.v1 import voice, workspace

api_router = APIRouter()
api_router.include_router(workspace.router)
api_router.include_router(voice.router)
