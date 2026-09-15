import os
import re
import sys
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List

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
from text_normalizer import normalize_vietnamese_text
from subtitle_generator import SubtitleGenerator

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
OUTPUTS_DIR = BASE_DIR / "outputs"
UPLOADS_DIR = BASE_DIR / "uploads"
WEB_DIR = BASE_DIR / "web"

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

voice_manager = VoiceManager(str(MODELS_DIR))

app = FastAPI(title="Viet Voice Studio - Clone & TTS Tiếng Việt", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TTSRequest(BaseModel):
    text: str
    voice: str = "vi-VN-NamMinhNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    pause_style: str = "natural"
    user_model_id: Optional[str] = None
    auto_normalize: bool = True

def format_natural_text(text: str, pause_style: str) -> str:
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

    processed = re.sub(
        r"[.,;:?!]*\s*\[(?:nghỉ|nghi|dừng|dung|pause)\s*([\d\.]+)\s*(?:s|giây|giay)?\]\s*[.,;:?!]*",
        replace_break_tag,
        text,
        flags=re.IGNORECASE
    )

    if pause_style == "long":
        processed = re.sub(r'([.?!]+)(?=\s|$)', r'... ', processed)

    processed = re.sub(r'\.{4,}', '...', processed)
    processed = re.sub(r'\.\s*\.\.\.', '...', processed)
    processed = re.sub(r'\.\.\.\s*\.', '...', processed)
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

@app.post("/api/normalize-text")
def api_normalize_text(data: dict):
    raw_text = data.get("text", "")
    return {"normalized_text": normalize_vietnamese_text(raw_text)}

@app.post("/api/tts")
async def generate_speech(req: TTSRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập văn bản cần đọc.")

    raw_text = req.text.strip()
    
    # 1. Chuẩn hóa viết tắt & số nếu được bật
    if req.auto_normalize:
        working_text = normalize_vietnamese_text(raw_text)
    else:
        working_text = raw_text

    # 2. Xử lý ngắt nghỉ tự nhiên
    clean_text = format_natural_text(working_text, req.pause_style)
    
    file_id = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    base_output_path = OUTPUTS_DIR / f"{file_id}_base.mp3"
    final_output_path = OUTPUTS_DIR / f"{file_id}.mp3"
    srt_output_path = OUTPUTS_DIR / f"{file_id}.srt"

    # 3. Tổng hợp giọng đọc & tạo phụ đề SRT
    success_tts = False
    last_error = None
    sub_generator = SubtitleGenerator()

    for attempt in range(4):
        try:
            communicate = edge_tts.Communicate(
                text=clean_text, 
                voice=req.voice, 
                rate=req.rate, 
                pitch=req.pitch,
                boundary="SentenceBoundary"
            )
            
            with open(base_output_path, "wb") as f_audio:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f_audio.write(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        sub_generator.feed(chunk)

            # Lưu file phụ đề SRT
            sub_generator.save_srt(str(srt_output_path))
            success_tts = True
            break
        except Exception as e:
            last_error = e
            print(f"[Edge-TTS Thử lại lần {attempt + 1}/4] {e}")
            await asyncio.sleep(1.5 * (attempt + 1))

    if not success_tts:
        print(f"[Lỗi Edge-TTS cuối cùng] {last_error}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi tổng hợp giọng nói: {str(last_error)}")

    # 4. Áp dụng model giọng cá nhân nếu có
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

    has_srt = srt_output_path.exists() and srt_output_path.stat().st_size > 0

    user_voice_name = "Giọng chuẩn AI"
    if req.user_model_id and req.user_model_id != "none":
        for m in voice_manager.list_models():
            if m["id"] == req.user_model_id:
                user_voice_name = m["name"]
                break

    return {
        "status": "success",
        "file_name": final_output_path.name,
        "audio_url": f"/api/audio/{final_output_path.name}",
        "subtitle_url": f"/api/subtitle/{srt_output_path.name}" if has_srt else None,
        "stats": {
            "word_count": word_count,
            "char_count": char_count,
            "voice": req.voice,
            "user_model": user_voice_name
        }
    }

@app.get("/api/audio/{filename}")
def get_audio_file(filename: str):
    file_path = OUTPUTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file âm thanh.")
    return FileResponse(path=file_path, media_type="audio/mpeg", filename=filename)

@app.get("/api/subtitle/{filename}")
def get_subtitle_file(filename: str):
    file_path = OUTPUTS_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file phụ đề.")
    return FileResponse(
        path=file_path, 
        media_type="text/plain; charset=utf-8", 
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/history")
def get_history():
    files = sorted(OUTPUTS_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    history = []
    for f in files[:25]:
        if f.name.endswith("_base.mp3"):
            continue
        srt_file = f.with_suffix(".srt")
        has_srt = srt_file.exists()
        history.append({
            "filename": f.name,
            "url": f"/api/audio/{f.name}",
            "subtitle_url": f"/api/subtitle/{srt_file.name}" if has_srt else None,
            "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M - %d/%m/%Y"),
            "size_kb": round(f.stat().st_size / 1024, 1)
        })
    return history

@app.post("/api/extract-clip-voice")
async def extract_clip_voice(
    file: UploadFile = File(...),
    voice_name: str = Form("")
):
    valid_exts = (
        ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v",
        ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"
    )
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in valid_exts:
        raise HTTPException(
            status_code=400, 
            detail=f"Định dạng {file_ext} không hỗ trợ. Vui lòng chọn file video hoặc audio."
        )

    clean_name = voice_name.strip() if voice_name else Path(file.filename).stem
    clean_name = re.sub(r'[^\w\s-]', '', clean_name).strip().replace(" ", "_")
    if not clean_name:
        clean_name = f"giong_clip_{uuid.uuid4().hex[:4]}"

    temp_input = UPLOADS_DIR / f"temp_{uuid.uuid4().hex[:8]}{file_ext}"
    try:
        with open(temp_input, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

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

@app.post("/api/extract-url-voice")
async def extract_url_voice(
    url: str = Form(...),
    voice_name: str = Form("")
):
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập đường link hợp lệ.")

    target_url = url.strip()
    clean_name = voice_name.strip() if voice_name else f"giong_url_{uuid.uuid4().hex[:4]}"
    clean_name = re.sub(r'[^\w\s-]', '', clean_name).strip().replace(" ", "_")

    try:
        result = voice_manager.extract_voice_from_url(
            url=target_url,
            voice_name=clean_name,
            uploads_dir=UPLOADS_DIR
        )
        return {
            "status": "success",
            "message": f"Tải và trích xuất thành công giọng từ link: {clean_name}",
            "voice": result,
            "models": voice_manager.list_models()
        }
    except Exception as e:
        print(f"[Lỗi trích xuất URL] {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi khi lấy giọng từ link: {str(e)}")

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

class RenameVoiceRequest(BaseModel):
    voice_id: str
    new_name: str

@app.post("/api/rename-voice")
def rename_voice_api(req: RenameVoiceRequest):
    if not req.voice_id or not req.new_name.strip():
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp đầy đủ ID và tên mới.")
    voice_manager.rename_voice(req.voice_id, req.new_name.strip())
    return {
        "status": "success",
        "message": f"Đã đổi tên giọng thành: {req.new_name.strip()}",
        "models": voice_manager.list_models()
    }

class DeleteVoiceRequest(BaseModel):
    voice_id: str

@app.post("/api/delete-voice")
def delete_voice_api(req: DeleteVoiceRequest):
    if not req.voice_id:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp ID giọng cần xóa.")
    voice_manager.delete_voice(req.voice_id)
    return {
        "status": "success",
        "message": "Đã xóa giọng thành công.",
        "models": voice_manager.list_models()
    }


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
    # Ưu tiên index.html ở root hoặc trong web/
    root_index = BASE_DIR / "index.html"
    web_index = WEB_DIR / "index.html"
    if root_index.exists():
        return FileResponse(root_index)
    if web_index.exists():
        return FileResponse(web_index)
    return JSONResponse({"message": "Web UI đang khởi tạo..."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7860, log_level="info")
