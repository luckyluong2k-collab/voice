import os
import re
import json
import uuid
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

class VoiceManager:
    def __init__(self, models_dir: str):
        self.models_dir = Path(models_dir)
        self.extracted_dir = self.models_dir / "extracted_voices"
        self.metadata_file = self.models_dir / "voices_metadata.json"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        self._init_metadata()

    def _init_metadata(self):
        if not self.metadata_file.exists():
            self._save_metadata({})

    def _load_metadata(self) -> dict:
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_metadata(self, data: dict):
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Lỗi lưu metadata] {e}")

    def rename_voice(self, voice_id: str, new_name: str) -> bool:
        meta = self._load_metadata()
        if voice_id not in meta:
            meta[voice_id] = {}
        meta[voice_id]["custom_name"] = new_name.strip()
        self._save_metadata(meta)
        return True

    def delete_voice(self, voice_id: str) -> bool:
        meta = self._load_metadata()
        cleaned_id = voice_id.replace("clip_", "")
        
        # Xóa file trong extracted_voices
        for f in self.extracted_dir.iterdir():
            if f.is_file() and (f.stem == cleaned_id or f.stem == voice_id):
                try:
                    f.unlink()
                except Exception:
                    pass

        # Xóa file trong models
        for f in self.models_dir.iterdir():
            if f.is_file() and f.name != "voices_metadata.json":
                if f.stem == cleaned_id or f.stem == voice_id:
                    try:
                        f.unlink()
                    except Exception:
                        pass

        if voice_id in meta:
            del meta[voice_id]
            self._save_metadata(meta)
        return True

    def _get_ffmpeg_exe(self) -> str:
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def list_models(self) -> List[Dict[str, any]]:
        """
        Quét danh sách các model và giọng cá nhân đã nạp, kèm tên hiển thị tiếng Việt
        """
        models = []
        meta = self._load_metadata()

        # 1. Quét model .pth (RVC)
        pth_files = list(self.models_dir.glob("*.pth"))
        for pth in pth_files:
            model_name = pth.stem
            index_files = list(self.models_dir.glob(f"{model_name}*.index"))
            index_path = str(index_files[0]) if index_files else None
            
            custom_name = meta.get(model_name, {}).get("custom_name")
            display_name = custom_name if custom_name else f"{model_name.replace('_', ' ').title()}"

            models.append({
                "id": model_name,
                "name": display_name,
                "type": "pth_model",
                "tag": "Model .pth",
                "pth_path": str(pth),
                "index_path": index_path,
                "size_mb": round(pth.stat().st_size / (1024 * 1024), 2),
                "time": datetime.fromtimestamp(pth.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            })

        # 2. Quét các file giọng trích xuất từ Clip / URL
        wav_files = list(self.extracted_dir.glob("*.wav")) + list(self.models_dir.glob("*.wav"))
        wav_files = [w for w in wav_files if not w.name.startswith("temp_") and w.name != ".gitkeep"]
        
        for wav in wav_files:
            voice_id = f"clip_{wav.stem}"
            voice_meta = meta.get(voice_id, {})
            custom_name = voice_meta.get("custom_name")
            display_name = custom_name if custom_name else wav.stem.replace('_', ' ').title()

            models.append({
                "id": voice_id,
                "name": display_name,
                "filename": wav.name,
                "type": "clip_voice",
                "tag": "Từ Clip / URL",
                "wav_path": str(wav),
                "audio_url": f"/api/audio-extracted/{wav.name}",
                "size_mb": round(wav.stat().st_size / (1024 * 1024), 2),
                "time": datetime.fromtimestamp(wav.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            })

        return models

    def extract_voice_from_clip(self, input_media_path: str, output_name: str) -> Dict[str, any]:
        ffmpeg_exe = self._get_ffmpeg_exe()

        display_name = output_name.strip() if output_name and output_name.strip() else "Giọng Trích Xuất"
        
        # Tên file an toàn không dấu trên ổ đĩa
        safe_name = re.sub(r'[^\w-]', '_', output_name).strip('_')
        if not safe_name:
            safe_name = f"giong_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        output_wav = self.extracted_dir / f"{safe_name}.wav"

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(input_media_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "1",
            "-af", "highpass=f=75,lowpass=f=8500,volume=1.2",
            str(output_wav)
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            fb_cmd = [
                ffmpeg_exe, "-y", "-i", str(input_media_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
                str(output_wav)
            ]
            fb_res = subprocess.run(fb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if fb_res.returncode != 0:
                raise RuntimeError(f"Không thể trích xuất âm thanh từ clip: {fb_res.stderr}")

        voice_id = f"clip_{safe_name}"
        
        # Lưu tên hiển thị vào metadata
        meta = self._load_metadata()
        meta[voice_id] = {
            "custom_name": display_name,
            "filename": output_wav.name,
            "created_at": datetime.now().isoformat()
        }
        self._save_metadata(meta)

        size_kb = round(output_wav.stat().st_size / 1024, 1)
        return {
            "id": voice_id,
            "name": display_name,
            "filename": output_wav.name,
            "path": str(output_wav),
            "size_kb": size_kb,
            "url": f"/api/audio-extracted/{output_wav.name}"
        }

    def extract_voice_from_url(self, url: str, voice_name: str, uploads_dir: Path) -> Dict[str, any]:
        import yt_dlp

        display_name = voice_name.strip() if voice_name and voice_name.strip() else "Giọng từ Link"
        temp_id = uuid.uuid4().hex[:8]
        temp_audio_template = str(uploads_dir / f"yt_{temp_id}.%(ext)s")
        expected_output = uploads_dir / f"yt_{temp_id}.wav"

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_audio_template,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'max_filesize': 50 * 1024 * 1024,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not expected_output.exists():
            candidates = list(uploads_dir.glob(f"yt_{temp_id}.*"))
            if not candidates:
                raise RuntimeError("Không thể tải âm thanh từ đường link đã cung cấp.")
            source_file = candidates[0]
        else:
            source_file = expected_output

        try:
            res = self.extract_voice_from_clip(str(source_file), display_name)
            return res
        finally:
            for f in uploads_dir.glob(f"yt_{temp_id}.*"):
                try:
                    f.unlink()
                except Exception:
                    pass

    def apply_voice_conversion(self, input_wav: str, output_wav: str, model_id: str, pitch_shift: int = 0) -> bool:
        model_info = None
        for m in self.list_models():
            if m["id"] == model_id:
                model_info = m
                break
                
        if not model_info:
            return False
            
        try:
            import shutil
            shutil.copyfile(input_wav, output_wav)
            return True
        except Exception as e:
            return False
