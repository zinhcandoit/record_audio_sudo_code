import io
import zipfile
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from backend.database import db_manager

router = APIRouter(prefix="/api/recordings", tags=["Recordings"])


@router.get("")
def list_recordings():
    """Lists all saved recordings with their metadata."""
    return db_manager.get_all_recordings()


@router.get("/{filename}")
def stream_recording_audio(filename: str):
    """
    Streams the MP3 audio file directly from MongoDB GridFS or local storage.
    """
    audio_bytes = db_manager.get_recording_audio(filename)
    if not audio_bytes:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file âm thanh '{filename}'")

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"inline; filename={filename}",
            "Accept-Ranges": "bytes"
        }
    )


@router.get("/export/zip")
def export_recordings_zip(reader_id: str = None):
    """
    Creates a ZIP archive containing all recorded MP3 files with the specified naming convention
    (D<XX>_YY_<gender>_<region>_<role>.mp3) and metadata JSON.
    Includes both finalized/committed recordings and staged recordings from ASR verification.
    """
    if reader_id:
        recordings = db_manager.get_all_available_recordings_for_reader(reader_id)
        zip_filename = f"recordings_{reader_id}.zip"
    else:
        recordings = db_manager.get_all_available_recordings()
        zip_filename = "all_recordings.zip"

    if not recordings:
        raise HTTPException(
            status_code=400,
            detail="Chưa có file thu âm nào để đóng gói ZIP. Vui lòng bấm 'Xác nhận & Kiểm tra toàn bộ' để kích hoạt thẩm định ASR ít nhất một lần."
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        files_added = 0
        for rec in recordings:
            fn = rec.get("filename")
            if not fn:
                continue
            audio_bytes = db_manager.get_recording_audio(fn)
            if audio_bytes:
                zip_file.writestr(fn, audio_bytes)
                files_added += 1

        if files_added == 0:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy file âm thanh để đóng gói ZIP."
            )

        # Also include metadata JSON (clean binary data)
        import json
        clean_records = [{k: v for k, v in r.items() if k != "audio_data"} for r in recordings]
        zip_file.writestr("metadata.json", json.dumps(clean_records, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )


@router.post("/reset/{reader_id}")
def reset_reader(reader_id: str):
    """
    Resets all recordings for a reader (for testing purposes).
    """
    db_manager.reset_reader_recordings(reader_id)
    return {"message": f"Đã xóa toàn bộ bản thu của người đọc '{reader_id}' thành công."}

