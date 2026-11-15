import os
from pathlib import Path

# Base directories
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = PROJECT_ROOT / "storage"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
(STORAGE_DIR / "mp3").mkdir(parents=True, exist_ok=True)

# Helper to load .env file manually without external dependency
def load_env_file(env_path: Path):
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key:
                    os.environ[key] = val

# Load .env from PROJECT_ROOT or current working directory
load_env_file(PROJECT_ROOT / ".env")
load_env_file(Path(".env"))

# Configurations
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

# MongoDB configurations
# Separated database names as required by specification:
# DB_NAME_SCRIPTS: stores telesale_cases_full.json and reader assignments
# DB_NAME_RECORDINGS: stores audio MP3 in GridFS and recording metadata
MONGODB_URI = os.getenv("MONGODB_URI", "")
DB_NAME_SCRIPTS = os.getenv("DB_NAME_SCRIPTS", "telesale_scripts_db")
DB_NAME_RECORDINGS = os.getenv("DB_NAME_RECORDINGS", "telesale_recordings_db")

# Thresholds for validation
RAPIDFUZZ_SCORE_THRESHOLD = float(os.getenv("RAPIDFUZZ_SCORE_THRESHOLD", "0.85"))
WPM_MIN_THRESHOLD = float(os.getenv("WPM_MIN_THRESHOLD", "4.0"))

# Server settings
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

