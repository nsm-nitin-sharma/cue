import re
import edge_tts
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import get_active_business_id, get_current_user
from app.db.supabase_client import get_admin_supabase
from app.domain.schemas.intents import (
    ConfirmOperationRequest,
    CreateProductAndExecuteRequest,
    OfflineSyncBatchRequest,
    TextCommandRequest,
    TtsRequest,
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


def _clean_tts_text(text: str, language: str) -> str:
    rupee_word = "rupees" if language == "en" else "rupaye"
    cleaned = re.sub(r"₹\s*([\d,]+(?:\.\d+)?)", lambda m: f"{m.group(1).replace(',', '')} {rupee_word}", text)
    cleaned = cleaned.replace("→", " to ")
    return re.sub(r"\s+", " ", cleaned).strip()


@router.post("/tts")
async def synthesize_natural_speech(
    req: TtsRequest,
    user: dict = Depends(get_current_user),
) -> Response:
    """Free Neural TTS using Microsoft Edge Indian voices (Neerja / Swara)."""
    _ = user
    spoken = _clean_tts_text(req.text, req.language)
    has_devanagari = any("\u0900" <= ch <= "\u097f" for ch in spoken)
    voice = "hi-IN-SwaraNeural" if (req.language == "hi" or has_devanagari) else "en-IN-NeerjaExpressiveNeural"
    try:
        comm = edge_tts.Communicate(spoken, voice, rate="+2%")
        audio_chunks: list[bytes] = []
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        audio_bytes = b"".join(audio_chunks)
        if not audio_bytes:
            raise HTTPException(status_code=502, detail="Empty TTS stream")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Neural TTS unavailable: {exc}") from exc
