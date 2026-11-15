from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List

from backend.database import db_manager

router = APIRouter(prefix="/api/readers", tags=["Readers"])


@router.get("", response_model=List[Dict[str, Any]])
def list_readers():
    """
    Returns available readers (Nữ 1, Nữ 2, etc.) and total turn counts.
    NO READING from telesale_recordings_db to sync: each reader is always available
    for fresh recording sessions so multiple voice takes can be captured in the database.
    """
    readers = db_manager.get_readers()
    result = []
    for r in readers:
        total_count = len(r.get("turns", []))
        result.append({
            "id": r["id"],
            "name": r.get("name", r["id"]),
            "gender": r.get("gender"),
            "region": r.get("region"),
            "role_description": r.get("role_description"),
            "total_turns": total_count,
            "completed_turns": 0,
            "is_completed": False
        })
    return result


@router.get("/{reader_id}/turns")
def get_reader_turns(reader_id: str):
    """
    Returns all assigned turns for the reader from the scripts database.
    NO READING from telesale_recordings_db to sync: turns always start fresh (pending)
    so each session records a new take with its own unique timestamp.
    """
    reader_info = db_manager.get_reader_turns(reader_id)
    if not reader_info:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người đọc '{reader_id}'")

    turns = []
    for t in reader_info.get("turns", []):
        filename = t.get("filename")
        turns.append({
            "dialogue_id": t["dialogue_id"],
            "turn_idx": t["turn_idx"],
            "speaker": t["speaker"],
            "role": t["role"],
            "gender": t["gender"],
            "region": t["region"],
            "text": t["text"],
            "filename": filename,
            "status": "pending",
            "locked": False,
            "audio_url": None,
            "score": None,
            "score_percent": None,
            "wpm": None,
            "duration": None,
            "asr_transcript": None,
            "recorded_time": None
        })

    return {
        "reader_id": reader_id,
        "name": reader_info.get("name"),
        "gender": reader_info.get("gender"),
        "region": reader_info.get("region"),
        "role_description": reader_info.get("role_description"),
        "total_turns": len(turns),
        "completed_turns": 0,
        "all_passed": False,
        "turns": turns
    }

