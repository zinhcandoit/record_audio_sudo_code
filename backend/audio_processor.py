import io
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

import rapidfuzz
from openai import OpenAI

from backend.config import (
    OPENAI_API_KEY,
    OPENAI_WHISPER_MODEL,
    RAPIDFUZZ_SCORE_THRESHOLD,
    WPM_MIN_THRESHOLD,
)

# Detect FFmpeg executable
def get_ffmpeg_executable() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return "ffmpeg"


def get_ffprobe_executable() -> Optional[str]:
    exe = shutil.which("ffprobe")
    return exe


def convert_audio_to_mp3(input_bytes: bytes, input_format: str = "webm") -> Tuple[bytes, float]:
    """
    Converts audio bytes into standardized MP3 (16kHz, mono, 128k bitrate).
    Returns (mp3_bytes, duration_seconds).
    """
    ffmpeg_exe = get_ffmpeg_executable()
    
    with tempfile.NamedTemporaryFile(suffix=f".{input_format}", delete=False) as in_file:
        in_file.write(input_bytes)
        in_path = in_file.name

    out_path = in_path + ".mp3"

    try:
        # ffmpeg convert command
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", in_path,
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "128k",
            out_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed: {res.stderr.decode('utf-8', errors='ignore')}")

        with open(out_path, "rb") as f:
            mp3_bytes = f.read()

        duration = get_audio_duration(out_path)
        return mp3_bytes, duration
    finally:
        if os.path.exists(in_path):
            try:
                os.remove(in_path)
            except Exception:
                pass
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass


def get_audio_duration(file_path: str) -> float:
    """Gets audio duration in seconds using ffprobe or ffmpeg."""
    ffprobe_exe = get_ffprobe_executable()
    if ffprobe_exe:
        cmd = [
            ffprobe_exe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0:
            try:
                return float(res.stdout.decode().strip())
            except ValueError:
                pass

    # Fallback to ffmpeg stderr parse
    ffmpeg_exe = get_ffmpeg_executable()
    cmd = [ffmpeg_exe, "-i", file_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = res.stderr.decode("utf-8", errors="ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)

    # Estimate based on MP3 size at 128kbps (16000 bytes/sec)
    try:
        size = os.path.getsize(file_path)
        return max(0.1, round(size / 16000.0, 2))
    except Exception:
        return 1.0


def count_vietnamese_words(text: str) -> int:
    """
    Counts words in Vietnamese text (tokens/syllables separated by whitespace).
    Excludes punctuation and special characters.
    """
    clean = re.sub(r"[^\w\s]", " ", text)
    tokens = [t for t in clean.split() if t]
    return max(1, len(tokens))


def calculate_wpm(text: str, duration_sec: float) -> float:
    """
    Calculates Words Per Minute (WPM) according to Vietnamese word count:
    WPM = (number_of_words / duration_in_seconds) * 60.0
    """
    if duration_sec <= 0:
        return 0.0
    words = count_vietnamese_words(text)
    wpm = (words / duration_sec) * 60.0
    return round(wpm, 2)


# Dictionary for mapping common Vietnamese digits to words
VIETNAMESE_NUMBERS = {
    "0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn",
    "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín",
    "10": "mười", "11": "mười một", "12": "mười hai", "13": "mười ba",
    "14": "mười bốn", "15": "mười lăm", "20": "hai mươi", "21": "hai mươi mốt",
    "22": "hai mươi hai", "25": "hai mươi lăm", "30": "ba mươi", "36": "ba mươi sáu",
    "40": "bốn mươi", "41": "bốn mươi mốt", "42": "bốn mươi hai", "43": "bốn mươi ba",
    "50": "năm mươi", "100": "một trăm",
}

def normalize_vietnamese_text(text: str) -> str:
    """
    Normalizes Vietnamese text for accurate RapidFuzz comparison:
    - Normalizes to Unicode NFC
    - Converts to lowercase
    - Replaces common abbreviations and numbers
    - Removes punctuation and collapses whitespace
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).lower()

    # Acronyms and specific terms
    text = re.sub(r"\bbtc\b", "bê tê xê", text)
    text = re.sub(r"\bm2\b|\bm²\b", "mét vuông", text)
    text = re.sub(r"\bcod\b", "xê ô đê", text)

    # Replace digits
    for num, word in VIETNAMESE_NUMBERS.items():
        text = re.sub(rf"\b{num}\b", word, text)

    # Strip punctuation
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def calculate_rapidfuzz_score(ground_truth: str, hypothesis: str) -> float:
    """
    Computes RapidFuzz similarity score between 0.0 and 1.0.
    """
    gt_norm = normalize_vietnamese_text(ground_truth)
    hyp_norm = normalize_vietnamese_text(hypothesis)

    if not gt_norm and not hyp_norm:
        return 1.0
    if not gt_norm or not hyp_norm:
        return 0.0

    ratio = rapidfuzz.fuzz.ratio(gt_norm, hyp_norm) / 100.0
    return round(ratio, 4)


def transcribe_with_whisper(audio_bytes: bytes, filename: str = "audio.mp3") -> str:
    """
    Sends MP3 audio to OpenAI Whisper API for speech-to-text.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY chưa được cấu hình. Vui lòng thiết lập OPENAI_API_KEY trong file .env")

    client = OpenAI(api_key=OPENAI_API_KEY)

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename

    transcript = client.audio.transcriptions.create(
        model=OPENAI_WHISPER_MODEL,
        file=audio_file,
        language="vi"
    )

    if hasattr(transcript, "text"):
        return transcript.text
    return str(transcript)


def evaluate_recording(
    ground_truth: str,
    audio_bytes: bytes,
    filename: str = "audio.mp3"
) -> Dict[str, Any]:
    """
    Runs complete verification pipeline:
    1. ASR via OpenAI Whisper
    2. RapidFuzz similarity score
    3. Vietnamese Word count & WPM
    4. Pass/Fail check against thresholds
    """
    # 1. ASR
    asr_text = transcribe_with_whisper(audio_bytes, filename=filename)

    # 2. RapidFuzz score
    score = calculate_rapidfuzz_score(ground_truth, asr_text)

    # 3. Audio duration and WPM
    # Write temp to calculate duration
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_bytes)
        tmp_name = f.name
    try:
        duration_sec = get_audio_duration(tmp_name)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except Exception:
                pass

    word_count = count_vietnamese_words(ground_truth)
    wpm = calculate_wpm(ground_truth, duration_sec)

    # 4. Evaluation checks
    score_passed = score >= RAPIDFUZZ_SCORE_THRESHOLD
    wpm_passed = wpm >= WPM_MIN_THRESHOLD
    passed = score_passed and wpm_passed

    reasons = []
    if not score_passed:
        reasons.append(
            f"Độ tương đồng nội dung thấp: {score * 100:.1f}% (Yêu cầu ≥ {RAPIDFUZZ_SCORE_THRESHOLD * 100:.0f}%). "
            f"Nhận dạng được: \"{asr_text}\""
        )
    if not wpm_passed:
        reasons.append(
            f"Tốc độ đọc quá chậm hoặc bản thu chứa nhiều khoảng lặng: {wpm:.1f} WPM (Yêu cầu ≥ {WPM_MIN_THRESHOLD:.1f} WPM)"
        )

    return {
        "passed": passed,
        "score": score,
        "score_percent": round(score * 100, 1),
        "score_passed": score_passed,
        "wpm": wpm,
        "wpm_passed": wpm_passed,
        "word_count": word_count,
        "duration_seconds": round(duration_sec, 2),
        "asr_transcript": asr_text,
        "ground_truth": ground_truth,
        "reasons": reasons,
    }

