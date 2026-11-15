import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from backend.config import RAPIDFUZZ_SCORE_THRESHOLD, WPM_MIN_THRESHOLD
from backend.database import db_manager
from backend.audio_processor import convert_audio_to_mp3, evaluate_recording

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/verify", tags=["Verification"])


@router.post("/turn")
async def verify_turn(
    reader_id: str = Form(...),
    dialogue_id: str = Form(...),
    turn_idx: int = Form(...),
    audio: UploadFile = File(...)
):
    """
    Receives an audio recording for a single turn, converts to MP3,
    runs OpenAI Whisper ASR, calculates RapidFuzz similarity score and WPM,
    and if passed, stores into MongoDB recordings database & GridFS.
    """
    reader_info = db_manager.get_reader_turns(reader_id)
    if not reader_info:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người đọc '{reader_id}'")

    # Locate assigned turn
    turn_item = next(
        (t for t in reader_info.get("turns", [])
         if t["dialogue_id"] == dialogue_id and t["turn_idx"] == turn_idx),
        None
    )
    if not turn_item:
        raise HTTPException(
            status_code=404,
            detail=f"Lượt thoại {dialogue_id} #{turn_idx} không thuộc phân công của {reader_id}"
        )

    ground_truth = turn_item["text"]
    expected_filename = turn_item["filename"]

    # Read uploaded audio
    raw_audio_bytes = await audio.read()
    if not raw_audio_bytes:
        raise HTTPException(status_code=400, detail="File âm thanh trống hoặc không hợp lệ")

    # 1. Convert to standardized MP3 (16kHz Mono 128k)
    try:
        mp3_bytes, duration_sec = convert_audio_to_mp3(raw_audio_bytes, input_format="webm")
    except Exception as e:
        logger.error(f"Error converting audio to MP3: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi chuyển đổi âm thanh: {str(e)}")

    # 2. Evaluate via OpenAI Whisper ASR + RapidFuzz + Vietnamese WPM
    eval_result = None
    try:
        eval_result = evaluate_recording(
            ground_truth=ground_truth,
            audio_bytes=mp3_bytes,
            filename=expected_filename
        )
    except ValueError as ve:
        logger.warning(f"Configuration/Validation warning: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        # Even if Whisper API fails, keep the audio and record error
        eval_result = {
            "asr_transcript": f"[Lỗi Whisper: {str(e)}]",
            "score": 0.0,
            "score_percent": 0.0,
            "score_passed": False,
            "passed": False,
            "wpm": 0.0,
            "wpm_passed": False,
            "word_count": 0,
            "duration_seconds": duration_sec,
            "reasons": [f"Lỗi Whisper ASR: {str(e)}"]
        }

    is_passed = eval_result["passed"]

    # 3. Handle Staging:
    # ALWAYS save the latest standardized MP3 into staging.
    # If the user re-recorded a turn because Whisper hallucinated (e.g. 'ừ'),
    # saving here ensures the NEW audio replaces the OLD audio, and ALL audio files
    # are preserved for the full .zip export!
    metadata = {
        "filename": expected_filename,
        "reader_id": reader_id,
        "reader_name": reader_info.get("name"),
        "dialogue_id": dialogue_id,
        "turn_idx": turn_idx,
        "speaker": turn_item["speaker"],
        "role": turn_item["role"],
        "gender": turn_item["gender"],
        "region": turn_item["region"],
        "ground_truth_text": ground_truth,
        "asr_transcript": eval_result.get("asr_transcript", ""),
        "rapidfuzz_score": eval_result.get("score", 0.0),
        "wpm": eval_result.get("wpm", 0.0),
        "word_count": eval_result.get("word_count", 0),
        "duration_seconds": eval_result.get("duration_seconds", duration_sec),
        "status": "passed" if is_passed else "failed",
        "reasons": eval_result.get("reasons", [])
    }
    db_manager.save_staging_turn(reader_id, metadata, mp3_bytes)

    return {
        "dialogue_id": dialogue_id,
        "turn_idx": turn_idx,
        "filename": expected_filename,
        "passed": is_passed,
        "score": eval_result["score"],
        "score_percent": eval_result["score_percent"],
        "score_passed": eval_result["score_passed"],
        "wpm": eval_result["wpm"],
        "wpm_passed": eval_result["wpm_passed"],
        "duration": eval_result["duration_seconds"],
        "word_count": eval_result["word_count"],
        "asr_transcript": eval_result["asr_transcript"],
        "ground_truth": ground_truth,
        "reasons": eval_result["reasons"],
        "staged": True,
        "audio_url": f"/api/recordings/{expected_filename}"
    }


@router.post("/stage-turn")
async def stage_turn_without_asr(
    reader_id: str = Form(...),
    dialogue_id: str = Form(...),
    turn_idx: int = Form(...),
    audio: UploadFile = File(...)
):
    """
    Directly converts a newly recorded audio turn to standardized MP3 and saves it to staging,
    overwriting any old recording for this turn.
    Ensures that when a user re-records a hallucinating turn (e.g. 'ừ'), the new audio
    is ready to be packaged into the .zip file immediately.
    """
    reader_info = db_manager.get_reader_turns(reader_id)
    if not reader_info:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người đọc '{reader_id}'")

    assigned_turns = reader_info.get("turns", [])
    turn_item = next((t for t in assigned_turns if t["dialogue_id"] == dialogue_id and t["turn_idx"] == turn_idx), None)
    if not turn_item:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy lượt {dialogue_id} #{turn_idx}")

    expected_filename = turn_item["filename"]
    raw_audio_bytes = await audio.read()

    try:
        mp3_bytes, duration_sec = convert_audio_to_mp3(raw_audio_bytes, input_format="webm")
    except Exception as e:
        logger.error(f"Error converting audio to MP3: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi chuyển đổi âm thanh: {str(e)}")

    metadata = {
        "filename": expected_filename,
        "reader_id": reader_id,
        "reader_name": reader_info.get("name"),
        "dialogue_id": dialogue_id,
        "turn_idx": turn_idx,
        "speaker": turn_item["speaker"],
        "role": turn_item["role"],
        "gender": turn_item["gender"],
        "region": turn_item["region"],
        "ground_truth_text": turn_item["text"],
        "asr_transcript": "[Ghi âm lại - Sẵn sàng xuất ZIP]",
        "rapidfuzz_score": 1.0,
        "wpm": 4.0,
        "duration_seconds": duration_sec,
        "status": "re-recorded",
        "reasons": []
    }
    db_manager.save_staging_turn(reader_id, metadata, mp3_bytes)

    return {
        "success": True,
        "filename": expected_filename,
        "audio_url": f"/api/recordings/{expected_filename}",
        "duration": duration_sec
    }


@router.delete("/turn/{reader_id}/{filename}")
def delete_turn_recording(reader_id: str, filename: str):
    """
    Deletes the staged recording for a specific turn when re-recording is requested.
    Ensures old failed recordings are completely wiped out.
    """
    db_manager.delete_staging_turn(reader_id, filename)
    return {"success": True, "deleted": filename}


@router.post("/finalize/{reader_id}")
def finalize_session(reader_id: str):
    """
    Commits all N turns for the reader to MongoDB ONLY if all N/N turns
    have been completed and verified.
    """
    try:
        result = db_manager.commit_completed_session(reader_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error committing session: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu dữ liệu vào MongoDB: {str(e)}")


@router.get("/status/{reader_id}")
def check_reader_status(reader_id: str):
    """
    Checks if all turns for this reader have been recorded and passed.
    Reports any missing turns or turns requiring re-recording.
    """
    reader_info = db_manager.get_reader_turns(reader_id)
    if not reader_info:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người đọc '{reader_id}'")

    assigned_turns = reader_info.get("turns", [])
    recordings = db_manager.get_recordings_by_reader(reader_id)
    recorded_map = {r["filename"]: r for r in recordings}

    missing_turns = []
    completed_turns = []

    for t in assigned_turns:
        fn = t["filename"]
        if fn in recorded_map and recorded_map[fn].get("status") == "passed":
            completed_turns.append(t)
        else:
            missing_turns.append(t)

    all_passed = (len(missing_turns) == 0 and len(assigned_turns) > 0)

    return {
        "reader_id": reader_id,
        "name": reader_info.get("name"),
        "total_assigned": len(assigned_turns),
        "completed_count": len(completed_turns),
        "missing_count": len(missing_turns),
        "all_passed": all_passed,
        "missing_turns": [
            {
                "dialogue_id": t["dialogue_id"],
                "turn_idx": t["turn_idx"],
                "filename": t["filename"],
                "text": t["text"]
            }
            for t in missing_turns
        ]
    }
