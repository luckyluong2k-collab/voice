import os
import re
import sys
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

# Đảm bảo UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import edge_tts
from voice_converter import VoiceManager

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BASE_DIR / "uploads"
WEB_DIR = BASE_DIR / "web"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

voice_manager = VoiceManager(str(MODELS_DIR))

app = FastAPI(title="Viet Voice Studio - Clone & TTS Tiếng Việt", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TTSRequest(BaseModel):
    text: str
    voice: str = "vi-VN-NamMinhNeural"  # hoặc vi-VN-HoaiMyNeural
    rate: str = "+0%"                  # -30% đến +50%
    pitch: str = "+0Hz"                # -50Hz đến +50Hz
    pause_style: str = "natural"       # natural, standard, long
    user_model_id: Optional[str] = None # ID model giọng cá nhân nếu có

def format_natural_text(text: str, pause_style: str) -> str:
    """
    Chuẩn hóa văn bản tiếng Việt để Microsoft Neural TTS ngắt nghỉ tự nhiên nhất:
    - Xử lý các tag [nghỉ 0.5s], [nghi 1s] thành khoảng dừng ngữ âm (... hoặc dấu phẩy ngắt dòng)
    - Tự động chuẩn hóa dấu câu tiếng Việt để không bị đọc dồn dập
    """
    def replace_break_tag(match):
        val_str = match.group(1).replace(",", ".")
        try:
            val = float(val_str)
            if val <= 0.4:
                return ", "
            elif val <= 1.0:
                return "... "
            else:
                return "...\n\n"
        except:
            return ", "

    # Xóa dấu câu liền kề trước hoặc sau tag [nghỉ ...] để tránh sinh ra dạng . ...
    processed = re.sub(
        r"[.,;:?!]*\s*\[(?:nghỉ|nghi|dừng|dung|pause)\s*([\d\.]+)\s*(?:s|giây|giay)?\]\s*[.,;:?!]*",
        replace_break_tag,
        text,
        flags=re.IGNORECASE
    )

    if pause_style == "long":
        processed = re.sub(r'([.?!]+)(?=\s|$)', r'... ', processed)

    # Loại bỏ lặp dấu chấm
    processed = re.sub(r'\.{4,}', '...', processed)
    processed = re.sub(r'\.\s*\.\.\.', '...', processed)
    processed = re.sub(r'\.\.\.\s*\.', '...', processed)

    # Chuẩn hóa khoảng trắng
    processed = re.sub(r'[ \t]+', ' ', processed)
    return processed.strip()

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "Viet Voice Studio",
        "time": datetime.now().isoformat()
    }

@app.get("/api/models")
def get_user_models():
    return {
        "models": voice_manager.list_models()
    }

@app.get("/api/voices")
def get_base_voices():
    return [
        {
            "id": "vi-VN-NamMinhNeural",
            "name": "Nam Minh (Giọng Nam - Trầm ấm, tự nhiên)",
            "gender": "Male",
            "region": "Miền Bắc & Chuẩn toàn quốc"
        },
        {
            "id": "vi-VN-HoaiMyNeural",
            "name": "Hoài My (Giọng Nữ - Nhẹ nhàng, truyền cảm)",
            "gender": "Female",
            "region": "Miền Bắc & Chuẩn toàn quốc"
        }
    ]

@app.post("/api/tts")
async def generate_speech(req: TTSRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập văn bản cần đọc.")

    raw_text = req.text.strip()
    clean_text = format_natural_text(raw_text, req.pause_style)
    
    file_id = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    base_output_path = OUTPUTS_DIR / f"{file_id}_base.mp3"
    final_output_path = OUTPUTS_DIR / f"{file_id}.mp3"

    # Tạo file âm thanh với cơ chế thử lại tự động (retry) chống nghẽn mạng
    success_tts = False
    last_error = None
    for attempt in range(4):
        try:
            communicate = edge_tts.Communicate(
                text=clean_text, 
                voice=req.voice, 
                rate=req.rate, 
                pitch=req.pitch
            )
            await communicate.save(str(base_output_path))
            success_tts = True
            break
        except Exception as e:
            last_error = e
            print(f"[Edge-TTS Thử lại lần {attempt + 1}/4] {e}")
            await asyncio.sleep(1.5 * (attempt + 1))

    if not success_tts:
        print(f"[Lỗi Edge-TTS cuối cùng] {last_error}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi tổng hợp giọng nói: {str(last_error)}")

    # Nếu có model cá nhân được chọn, thực hiện chuyển giọng
    if req.user_model_id and req.user_model_id != "none":
        success = voice_manager.apply_voice_conversion(
            input_wav=str(base_output_path),
            output_wav=str(final_output_path),
            model_id=req.user_model_id
        )
        if not success:
            final_output_path = base_output_path
    else:
        final_output_path = base_output_path

    word_count = len(raw_text.split())
    char_count = len(raw_text)

    return {
        "status": "success",
        "file_name": final_output_path.name,
        "audio_url": f"/api/audio/{final_output_path.name}",
        "stats": {
            "word_count": word_count,
            "char_count": char_count,
            "voice": req.voice,
            "user_model": req.user_model_id or "Giọng gốc"
        }
    }

@app.get("/api/audio/{filename}")
def get_audio_file(filename: str):
    file_path = OUTPUTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file âm thanh.")
    return FileResponse(path=file_path, media_type="audio/mpeg", filename=filename)

@app.get("/api/history")
def get_history():
    files = sorted(OUTPUTS_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    history = []
    for f in files[:20]:
        if f.name.endswith("_base.mp3"):
            continue
        history.append({
            "filename": f.name,
            "url": f"/api/audio/{f.name}",
            "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M - %d/%m/%Y"),
            "size_kb": round(f.stat().st_size / 1024, 1)
        })
    return history

@app.post("/api/upload-model")
async def upload_model(file: UploadFile = File(...)):
    if not (file.filename.endswith(".pth") or file.filename.endswith(".index")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file model .pth hoặc .index")
    
    save_path = MODELS_DIR / file.filename
    with open(save_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    return {
        "status": "success",
        "message": f"Đã lưu thành công model: {file.filename}",
        "models": voice_manager.list_models()
    }

@app.post("/api/extract-clip-voice")
async def extract_clip_voice(
    file: UploadFile = File(...),
    voice_name: str = Form("")
):
    """
    Trích xuất âm thanh giọng nói từ file video hoặc audio clip.
    Hỗ trợ .mp4, .mov, .mkv, .avi, .webm, .mp3, .m4a, v.v.
    """
    valid_exts = (
        ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v",
        ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"
    )
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in valid_exts:
        raise HTTPException(
            status_code=400, 
            detail=f"Định dạng {file_ext} không hỗ trợ. Vui lòng chọn file video (mp4, mov, mkv, webm...) hoặc audio (mp3, wav, m4a...)"
        )

    # Chuẩn hóa tên giọng
    clean_name = voice_name.strip() if voice_name else Path(file.filename).stem
    clean_name = re.sub(r'[^\w\s-]', '', clean_name).strip().replace(" ", "_")
    if not clean_name:
        clean_name = f"giong_clip_{uuid.uuid4().hex[:4]}"

    # Lưu tạm clip vào thư mục uploads
    temp_input = UPLOADS_DIR / f"temp_{uuid.uuid4().hex[:8]}{file_ext}"
    try:
        with open(temp_input, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Trích xuất giọng bằng FFmpeg
        result = voice_manager.extract_voice_from_clip(
            input_media_path=str(temp_input),
            output_name=clean_name
        )

        return {
            "status": "success",
            "message": f"Trích xuất thành công giọng từ clip: {clean_name}",
            "voice": result,
            "models": voice_manager.list_models()
        }
    except Exception as e:
        print(f"[Lỗi trích xuất clip] {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi trích xuất giọng từ clip: {str(e)}")
    finally:
        if temp_input.exists():
            try:
                temp_input.unlink()
            except Exception:
                pass

@app.get("/api/audio-extracted/{filename}")
def get_extracted_audio(filename: str):
    file_path = voice_manager.extracted_dir / filename
    if not file_path.exists():
        file_path = MODELS_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Không tìm thấy file âm thanh trích xuất.")
    return FileResponse(path=file_path, media_type="audio/wav", filename=filename)

@app.get("/")
def serve_index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse({"message": "Web UI đang khởi tạo..."})
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    import sys
    
    if "--test" in sys.argv:
        print("[Test] Đang kiểm tra sinh giọng nói mẫu...")
        async def run_test():
            comm = edge_tts.Communicate("Xin chào, đây là bài kiểm tra âm thanh tiếng Việt từ Viet Voice Studio.", "vi-VN-NamMinhNeural")
            test_file = OUTPUTS_DIR / "test.mp3"
            await comm.save(str(test_file))
            print(f"[Test Thành Công] File đã tạo: {test_file} ({test_file.stat().st_size} bytes)")
        asyncio.run(run_test())
        sys.exit(0)
        
    print("=" * 60)
    print("  VIET VOICE STUDIO - CÔNG CỤ NHÂN BẢN GIỌNG NÓI & TTS")
    print("  Đang chạy tại: http://127.0.0.1:7860")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="info")
