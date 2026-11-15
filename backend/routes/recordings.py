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
    Creates a ZIP archive containing all passed MP3 files and their metadata JSON.
    """
    if reader_id:
        recordings = db_manager.get_recordings_by_reader(reader_id)
        zip_filename = f"recordings_{reader_id}.zip"
    else:
        recordings = db_manager.get_all_recordings()
        zip_filename = "all_recordings.zip"

    if not recordings:
        raise HTTPException(status_code=404, detail="Chưa có bản thu âm nào hoàn tất để tải về")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for rec in recordings:
            fn = rec.get("filename")
            audio_bytes = db_manager.get_recording_audio(fn)
            if audio_bytes:
                zip_file.writestr(fn, audio_bytes)

        # Also include metadata JSON
        import json
        zip_file.writestr("metadata.json", json.dumps(recordings, ensure_ascii=False, indent=2))

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

