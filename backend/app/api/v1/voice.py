from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import get_active_business_id, get_current_user
from app.db.supabase_client import get_admin_supabase
from app.domain.schemas.intents import (
    ConfirmOperationRequest,
    CreateProductAndExecuteRequest,
    OfflineSyncBatchRequest,
    TextCommandRequest,
    VoiceTurnResult,
)
from app.services.voice_pipeline import VoicePipelineService

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/turn", response_model=VoiceTurnResult)
async def voice_audio_turn(
    audio: UploadFile = File(...),
    operation_id: str = Form(..., min_length=8, max_length=64),
    language: str = Form("hinglish"),
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> VoiceTurnResult:
    audio_bytes = await audio.read()
    pipeline = VoicePipelineService(get_admin_supabase())
    return await pipeline.process_audio_turn(
        business_id=business_id,
        user_id=user["user_id"],
        audio_bytes=audio_bytes,
        filename=audio.filename or "recording.webm",
        content_type=audio.content_type,
        operation_id=operation_id,
        language=language,
    )


@router.post("/text", response_model=VoiceTurnResult)
async def voice_text_turn(
    req: TextCommandRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> VoiceTurnResult:
    pipeline = VoicePipelineService(get_admin_supabase())
    return await pipeline.process_text_turn(
        business_id=business_id,
        user_id=user["user_id"],
        text=req.text,
        operation_id=req.operation_id,
        language=req.language,
    )


@router.post("/confirm", response_model=VoiceTurnResult)
def confirm_tier3_operation(
    req: ConfirmOperationRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> VoiceTurnResult:
    pipeline = VoicePipelineService(get_admin_supabase())
    return pipeline.confirm_tier3(
        business_id=business_id,
        user_id=user["user_id"],
        req=req,
    )


@router.post("/create-entity", response_model=VoiceTurnResult)
def create_product_from_popup(
    req: CreateProductAndExecuteRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> VoiceTurnResult:
    pipeline = VoicePipelineService(get_admin_supabase())
    return pipeline.create_product_and_execute(
        business_id=business_id,
        user_id=user["user_id"],
        req=req,
    )


@router.post("/sync-batch")
async def sync_offline_batch(
    req: OfflineSyncBatchRequest,
    user: dict = Depends(get_current_user),
    business_id: str = Depends(get_active_business_id),
) -> dict:
    """Replays queued offline operations strictly in FIFO chronological order."""
    pipeline = VoicePipelineService(get_admin_supabase())
    results = []
    for item in req.items:
        res = await pipeline.process_text_turn(
            business_id=business_id,
            user_id=user["user_id"],
            text=item.text,
            operation_id=item.operation_id,
            language=item.language,
            stt_provider="offline_sync",
        )
        results.append(res.model_dump())
    return {"synced_count": len(results), "results": results}
