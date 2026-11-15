from fastapi import APIRouter
from backend.config import (
    OPENAI_API_KEY,
    OPENAI_WHISPER_MODEL,
    MONGODB_URI,
    DB_NAME_SCRIPTS,
    DB_NAME_RECORDINGS,
    RAPIDFUZZ_SCORE_THRESHOLD,
    WPM_MIN_THRESHOLD,
)
from backend.database import db_manager
from backend.audio_processor import get_ffmpeg_executable

router = APIRouter(prefix="/api/system", tags=["System"])


@router.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}


@router.api_route("/status", methods=["GET", "HEAD"])
def get_system_status():
    """Returns the operational status of all backend subsystems."""
    # If not connected, give it another chance to connect in case Atlas whitelist was updated
    if not db_manager.is_connected:
        db_manager.connect()
        if db_manager.is_connected:
            try:
                db_manager.seed_scripts_database(force=False)
            except Exception:
                pass
    ffmpeg_exe = get_ffmpeg_executable()

    masked_key = ""
    if OPENAI_API_KEY:
        if len(OPENAI_API_KEY) > 8:
            masked_key = OPENAI_API_KEY[:4] + "..." + OPENAI_API_KEY[-4:]
        else:
            masked_key = "***"

    outbound_ip = db_manager.get_public_ip() if not db_manager.is_connected else None

    mongo_info = {
        "connected": db_manager.is_connected,
        "scripts_db": DB_NAME_SCRIPTS,
        "recordings_db": DB_NAME_RECORDINGS,
        "error": db_manager.connection_error,
        "outbound_ip": outbound_ip,
    }

    if db_manager.is_connected and db_manager.scripts_db is not None:
        try:
            mongo_info["dialogues_count"] = db_manager.scripts_db["dialogues"].count_documents({})
            mongo_info["assignments_count"] = db_manager.scripts_db["assignments"].count_documents({})
        except Exception:
            pass

    if db_manager.is_connected and db_manager.recordings_db is not None:
        try:
            mongo_info["recordings_count"] = db_manager.recordings_db["recordings"].count_documents({})
        except Exception:
            pass

    return {
        "status": "online",
        "mongodb": mongo_info,
        "openai": {
            "configured": bool(OPENAI_API_KEY),
            "model": OPENAI_WHISPER_MODEL,
            "api_key_masked": masked_key
        },
        "ffmpeg": {
            "executable": ffmpeg_exe
        },
        "thresholds": {
            "rapidfuzz_min_score": RAPIDFUZZ_SCORE_THRESHOLD,
            "rapidfuzz_min_percent": RAPIDFUZZ_SCORE_THRESHOLD * 100,
            "wpm_min": WPM_MIN_THRESHOLD
        }
    }


@router.post("/reconnect-db")
def reconnect_database():
    """Triggers an on-demand database reconnection attempt."""
    success = db_manager.connect()
    if success:
        try:
            db_manager.seed_scripts_database(force=False)
        except Exception:
            pass
    return {
        "connected": db_manager.is_connected,
        "error": db_manager.connection_error,
        "outbound_ip": db_manager.get_public_ip()
    }

