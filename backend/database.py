import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from pymongo import MongoClient, ASCENDING
import gridfs
from bson import ObjectId, Binary

from backend.config import (
    MONGODB_URI,
    DB_NAME_SCRIPTS,
    DB_NAME_RECORDINGS,
    DATA_DIR,
    STORAGE_DIR,
)

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.scripts_db = None
        self.recordings_db = None
        self.fs = None
        self.is_connected = False
        self.connection_error = None

        self.local_recordings_file = STORAGE_DIR / "recordings.json"
        self._init_local_storage()
        self.connect()

    def _init_local_storage(self):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        (STORAGE_DIR / "mp3").mkdir(parents=True, exist_ok=True)
        if not self.local_recordings_file.exists():
            with open(self.local_recordings_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def connect(self):
        """Attempts to connect to MongoDB."""
        import os
        uri = os.getenv("MONGODB_URI", MONGODB_URI)
        scripts_db_name = os.getenv("DB_NAME_SCRIPTS", DB_NAME_SCRIPTS)
        recordings_db_name = os.getenv("DB_NAME_RECORDINGS", DB_NAME_RECORDINGS)

        if not uri:
            self.is_connected = False
            self.connection_error = "MONGODB_URI chưa được thiết lập trong biến môi trường (.env)"
            logger.warning(self.connection_error)
            return

        try:
            self.client = MongoClient(uri, serverSelectionTimeoutMS=4000)
            # Ping database to confirm connection
            self.client.admin.command("ping")
            self.scripts_db = self.client[scripts_db_name]
            self.recordings_db = self.client[recordings_db_name]
            self.fs = gridfs.GridFS(self.recordings_db)
            self.is_connected = True
            self.connection_error = None
            logger.info(f"MongoDB connected successfully! Scripts DB: '{scripts_db_name}', Recordings DB: '{recordings_db_name}'")
        except Exception as e:
            self.is_connected = False
            self.connection_error = str(e)
            logger.warning(f"Could not connect to MongoDB: {e}. Running in local storage fallback mode.")

    def seed_scripts_database(self, force: bool = False):
        """
        Seeds telesale_cases_full.json and reader assignments into DB_NAME_SCRIPTS.
        """
        if not self.is_connected or self.scripts_db is None:
            logger.info("MongoDB not connected; skipping database seeding.")
            return

        dialogues_col = self.scripts_db["dialogues"]
        assignments_col = self.scripts_db["assignments"]

        # 1. Seed Dialogues
        if force or dialogues_col.count_documents({}) == 0:
            full_file = DATA_DIR / "telesale_cases_full.json"
            if full_file.exists():
                with open(full_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dialogues = data.get("dialogues", [])
                if dialogues:
                    dialogues_col.delete_many({})
                    dialogues_col.insert_many(dialogues)
                    dialogues_col.create_index([("id", ASCENDING)], unique=True)
                    logger.info(f"Seeded {len(dialogues)} dialogues into '{DB_NAME_SCRIPTS}.dialogues'")

        # 2. Seed Assignments
        if force or assignments_col.count_documents({}) == 0:
            assign_file = DATA_DIR / "assignments.json"
            if assign_file.exists():
                with open(assign_file, "r", encoding="utf-8") as f:
                    assignments = json.load(f)
                if assignments:
                    assignments_col.delete_many({})
                    assignments_col.insert_many(assignments)
                    assignments_col.create_index([("id", ASCENDING)], unique=True)
                    logger.info(f"Seeded {len(assignments)} readers into '{DB_NAME_SCRIPTS}.assignments'")

    def get_readers(self) -> List[Dict[str, Any]]:
        """Returns the list of readers with their assignment metadata."""
        if self.is_connected and self.scripts_db is not None:
            cursor = self.scripts_db["assignments"].find({}, {"_id": 0})
            readers = list(cursor)
            if readers:
                return readers

        # Fallback to local assignments.json
        assign_file = DATA_DIR / "assignments.json"
        if assign_file.exists():
            with open(assign_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_reader_turns(self, reader_id: str) -> Optional[Dict[str, Any]]:
        """Returns assignment details and turns for a specific reader."""
        readers = self.get_readers()
        for r in readers:
            if r["id"] == reader_id:
                return r
        return None

    def save_staging_turn(self, reader_id: str, metadata: Dict[str, Any], mp3_bytes: bytes):
        """
        Saves a verified turn to local staging (temporary storage).
        DOES NOT touch MongoDB yet!
        """
        staging_dir = STORAGE_DIR / "staging" / reader_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        filename = metadata["filename"]

        # 1. Save staged mp3
        with open(staging_dir / filename, "wb") as f:
            f.write(mp3_bytes)

        # 2. Save staged metadata json
        meta_file = staging_dir / f"{filename}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def get_staging_turns(self, reader_id: str) -> Dict[str, Dict[str, Any]]:
        """Returns all currently staged turns for this reader."""
        staging_dir = STORAGE_DIR / "staging" / reader_id
        if not staging_dir.exists():
            return {}
        result = {}
        for meta_file in staging_dir.glob("*.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    result[meta["filename"]] = meta
            except Exception:
                pass
        return result

    def commit_completed_session(self, reader_id: str) -> Dict[str, Any]:
        """
        COMMITS TO MONGODB ONLY WHEN ALL N/N TURNS FOR THE ROLE ARE COMPLETED AND VERIFIED.
        Saves BOTH the metadata and the raw MP3 binary data (in GridFS + audio_data BSON field).
        """
        reader_info = self.get_reader_turns(reader_id)
        if not reader_info:
            raise ValueError(f"Không tìm thấy người đọc '{reader_id}'")

        assigned_turns = reader_info.get("turns", [])
        total_required = len(assigned_turns)
        staging_dir = STORAGE_DIR / "staging" / reader_id

        if not staging_dir.exists():
            raise ValueError(f"Chưa có bản thu nào được thẩm định cho người đọc '{reader_id}'")

        # 1. Validate that ALL N turns exist in staging and PASSED
        staged_items = []
        missing = []
        for t in assigned_turns:
            fn = t["filename"]
            mp3_path = staging_dir / fn
            meta_path = staging_dir / f"{fn}.json"

            if not mp3_path.exists() or not meta_path.exists():
                missing.append(fn)
                continue

            with open(mp3_path, "rb") as f:
                mp3_bytes = f.read()
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            if meta.get("status") != "passed":
                missing.append(fn)
                continue

            staged_items.append((meta, mp3_bytes))

        if missing or len(staged_items) != total_required:
            raise ValueError(
                f"Chỉ lưu vào Database khi hoàn tất đủ {total_required}/{total_required} đoạn đạt chuẩn! "
                f"Còn thiếu hoặc chưa đạt: {missing}"
            )

        # 2. All N/N turns are passed -> Commit to MongoDB!
        commit_time = datetime.now(timezone.utc).isoformat()
        committed_filenames = []

        for meta, mp3_bytes in staged_items:
            fn = meta["filename"]
            meta["recorded_time"] = commit_time
            meta["updated_at"] = commit_time
            meta["file_size_bytes"] = len(mp3_bytes)
            meta["audio_format"] = "mp3"
            meta["audio_mime_type"] = "audio/mpeg"

            # Save to permanent local disk backup
            local_mp3 = STORAGE_DIR / "mp3" / fn
            with open(local_mp3, "wb") as f:
                f.write(mp3_bytes)
            self._update_local_recordings_json(meta)

            # Save to MongoDB: BOTH GridFS (chunks) and collection recordings (with raw audio_data)
            if self.is_connected and self.recordings_db is not None and self.fs is not None:
                # Remove previous GridFS file if exists
                old_file = self.recordings_db["fs.files"].find_one({"filename": fn})
                if old_file:
                    self.fs.delete(old_file["_id"])

                # 1. Save binary MP3 into GridFS
                gridfs_id = self.fs.put(
                    mp3_bytes,
                    filename=fn,
                    content_type="audio/mpeg",
                    reader_id=reader_id,
                    dialogue_id=meta["dialogue_id"],
                    turn_idx=meta["turn_idx"],
                    recorded_time=commit_time
                )
                meta["gridfs_id"] = str(gridfs_id)

                # 2. Save document into recordings collection WITH raw binary audio
                doc_to_save = dict(meta)
                doc_to_save["audio_data"] = Binary(mp3_bytes)

                self.recordings_db["recordings"].update_one(
                    {"filename": fn},
                    {"$set": doc_to_save},
                    upsert=True
                )

            committed_filenames.append(fn)

        # Clean staging directory
        try:
            import shutil
            shutil.rmtree(staging_dir, ignore_errors=True)
        except Exception:
            pass

        logger.info(f"Committed all {len(committed_filenames)} recordings for '{reader_id}' to MongoDB at {commit_time}")

        return {
            "success": True,
            "reader_id": reader_id,
            "reader_name": reader_info.get("name"),
            "total_committed": len(committed_filenames),
            "recorded_time": commit_time,
            "filenames": committed_filenames
        }

    def _update_local_recordings_json(self, metadata: Dict[str, Any]):
        try:
            with open(self.local_recordings_file, "r", encoding="utf-8") as f:
                records = json.load(f)
            records = [r for r in records if r.get("filename") != metadata["filename"]]
            meta_clean = {k: v for k, v in metadata.items() if k != "audio_data"}
            records.append(meta_clean)
            with open(self.local_recordings_file, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error updating local recordings JSON: {e}")

    def get_recording_audio(self, filename: str) -> Optional[bytes]:
        """Fetches MP3 bytes from MongoDB GridFS, document audio_data, staging, or local storage."""
        # 1. Check MongoDB document audio_data or GridFS
        if self.is_connected and self.recordings_db is not None:
            doc = self.recordings_db["recordings"].find_one({"filename": filename}, {"audio_data": 1})
            if doc and "audio_data" in doc and doc["audio_data"]:
                return bytes(doc["audio_data"])
            if self.fs is not None:
                grid_out = self.fs.find_one({"filename": filename})
                if grid_out:
                    return grid_out.read()

        # 2. Check staging directory (for previewing during verification)
        for staging_reader_dir in (STORAGE_DIR / "staging").glob("*"):
            staged_file = staging_reader_dir / filename
            if staged_file.exists():
                with open(staged_file, "rb") as f:
                    return f.read()

        # 3. Check permanent local storage
        local_path = STORAGE_DIR / "mp3" / filename
        if local_path.exists():
            with open(local_path, "rb") as f:
                return f.read()

        return None

    def get_recordings_by_reader(self, reader_id: str) -> List[Dict[str, Any]]:
        """Returns all officially saved recordings for a given reader from MongoDB."""
        if self.is_connected and self.recordings_db is not None:
            try:
                # Omit binary audio_data in list query to keep payload lightweight
                cursor = self.recordings_db["recordings"].find(
                    {"reader_id": reader_id, "status": "passed"},
                    {"_id": 0, "audio_data": 0}
                )
                return list(cursor)
            except Exception as e:
                logger.warning(f"MongoDB query failed: {e}")

        # Fallback to local file
        if self.local_recordings_file.exists():
            with open(self.local_recordings_file, "r", encoding="utf-8") as f:
                records = json.load(f)
                return [r for r in records if r.get("reader_id") == reader_id and r.get("status") == "passed"]
        return []

    def get_all_recordings(self) -> List[Dict[str, Any]]:
        """Returns all recordings saved in the system from MongoDB."""
        if self.is_connected and self.recordings_db is not None:
            try:
                cursor = self.recordings_db["recordings"].find({}, {"_id": 0, "audio_data": 0})
                return list(cursor)
            except Exception as e:
                logger.warning(f"MongoDB query failed: {e}")

        if self.local_recordings_file.exists():
            with open(self.local_recordings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def reset_reader_recordings(self, reader_id: str):
        """Clears all recordings for a specific reader (for re-testing)."""
        # MongoDB
        if self.is_connected and self.recordings_db is not None:
            try:
                # Find GridFS files
                files = self.recordings_db["recordings"].find({"reader_id": reader_id})
                for doc in files:
                    fn = doc.get("filename")
                    grid_file = self.recordings_db["fs.files"].find_one({"filename": fn})
                    if grid_file:
                        self.fs.delete(grid_file["_id"])
                self.recordings_db["recordings"].delete_many({"reader_id": reader_id})
            except Exception as e:
                logger.warning(f"Failed to clear MongoDB recordings: {e}")

        # Local
        if self.local_recordings_file.exists():
            try:
                with open(self.local_recordings_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
                records = [r for r in records if r.get("reader_id") != reader_id]
                with open(self.local_recordings_file, "w", encoding="utf-8") as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Failed to clear local recordings: {e}")

        # Clear staging
        staging_dir = STORAGE_DIR / "staging" / reader_id
        if staging_dir.exists():
            try:
                import shutil
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass

# Global database manager instance
db_manager = DatabaseManager()

