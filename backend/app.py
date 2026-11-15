import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import FRONTEND_DIR, PORT, HOST
from backend.database import db_manager
from backend.routes.readers import router as readers_router
from backend.routes.verify import router as verify_router
from backend.routes.recordings import router as recordings_router
from backend.routes.system import router as system_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure connection and seed scripts DB if connected and empty
    logger.info("Application starting up...")
    if not db_manager.is_connected:
        db_manager.connect()
    if db_manager.is_connected:
        try:
            db_manager.seed_scripts_database(force=False)
        except Exception as e:
            logger.warning(f"Auto-seed check failed on startup: {e}")
    else:
        logger.info("MongoDB not connected. Operating in local-mode.")
    yield
    # Shutdown
    logger.info("Application shutting down...")


app = FastAPI(
    title="Hệ Thống Thu Âm Telesale & Đánh Giá Giọng Nữ Bắc",
    description="Ứng dụng thu âm, nhận dạng giọng nói ASR Whisper, tính RapidFuzz và WPM theo chuẩn tiếng Việt",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(readers_router)
app.include_router(verify_router)
app.include_router(recordings_router)
app.include_router(system_router)

# Mount frontend static files
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
(FRONTEND_DIR / "css").mkdir(parents=True, exist_ok=True)
(FRONTEND_DIR / "js").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Frontend chưa được khởi tạo. Vui lòng kiểm tra thư mục frontend."}


@app.websocket("/")
@app.websocket("/ws")
async def websocket_fallback(websocket: WebSocket):
    """
    Handles WebSocket handshake requests gracefully.
    Prevents 403 Forbidden logs when browser extensions or tools (Live Server, DevTools)
    attempt to probe ws://localhost:8000/
    """
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=HOST, port=PORT, reload=True)

