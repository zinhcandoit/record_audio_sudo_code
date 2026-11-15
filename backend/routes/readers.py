from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List

from backend.database import db_manager

router = APIRouter(prefix="/api/readers", tags=["Readers"])


@router.get("", response_model=List[Dict[str, Any]])
def list_readers():
    """Returns available readers (Nữ 1, Nữ 2, etc.) and summary counts."""
    readers = db_manager.get_readers()
    result = []
    for r in readers:
        reader_id = r["id"]
        recordings = db_manager.get_recordings_by_reader(reader_id)
        passed_count = len(recordings)
        total_count = len(r.get("turns", []))
        result.append({
            "id": reader_id,
            "name": r.get("name", reader_id),
            "gender": r.get("gender"),
            "region": r.get("region"),
            "role_description": r.get("role_description"),
            "total_turns": total_count,
            "completed_turns": passed_count,
            "is_completed": (passed_count == total_count and total_count > 0)
        })
    return result


@router.get("/{reader_id}/turns")
def get_reader_turns(reader_id: str):
    """
    Returns all assigned turns for the reader, merged with existing recording status.
    """
    reader_info = db_manager.get_reader_turns(reader_id)
    if not reader_info:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người đọc '{reader_id}'")

    existing_recordings = db_manager.get_recordings_by_reader(reader_id)
    recordings_map = {r["filename"]: r for r in existing_recordings}
    staged_map = db_manager.get_staging_turns(reader_id)

    turns = []
    all_passed = True
    for t in reader_info.get("turns", []):
        filename = t.get("filename")
        rec = recordings_map.get(filename) or staged_map.get(filename)
        turn_data = {
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
        }

        if rec and rec.get("status") == "passed":
            turn_data["status"] = "passed"
            turn_data["locked"] = True
            turn_data["audio_url"] = f"/api/recordings/{filename}"
            turn_data["score"] = rec.get("rapidfuzz_score")
            turn_data["score_percent"] = round(rec.get("rapidfuzz_score", 0) * 100, 1)
            turn_data["wpm"] = rec.get("wpm")
            turn_data["duration"] = rec.get("duration_seconds")
            turn_data["asr_transcript"] = rec.get("asr_transcript")
            turn_data["recorded_time"] = rec.get("recorded_time") or rec.get("updated_at")
            turn_data["is_committed"] = (filename in recordings_map)
        else:
            all_passed = False

        turns.append(turn_data)

    total_turns = len(turns)
    completed_turns = sum(1 for t in turns if t["status"] == "passed")
    committed_turns = len(recordings_map)
    is_committed_all = (committed_turns == total_turns and total_turns > 0)

    return {
        "reader_id": reader_id,
        "name": reader_info.get("name"),
        "gender": reader_info.get("gender"),
        "region": reader_info.get("region"),
        "role_description": reader_info.get("role_description"),
        "total_turns": total_turns,
        "completed_turns": completed_turns,
        "committed_turns": committed_turns,
        "is_committed_all": is_committed_all,
        "all_passed": all_passed and total_turns > 0,
        "turns": turns
    }

