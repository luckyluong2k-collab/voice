import os
import re
import uuid
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

class VoiceManager:
    def __init__(self, models_dir: str):
        self.models_dir = Path(models_dir)
        self.extracted_dir = self.models_dir / "extracted_voices"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_ffmpeg_exe(self) -> str:
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

    def list_models(self) -> List[Dict[str, str]]:
        """
        Quét danh sách các model giọng cá nhân đã nạp trong thư mục models/
        """
        models = []
        
        # 1. Quét model .pth (RVC)
        pth_files = list(self.models_dir.glob("*.pth"))
        for pth in pth_files:
            model_name = pth.stem
            index_files = list(self.models_dir.glob(f"{model_name}*.index"))
            index_path = str(index_files[0]) if index_files else None
            
            models.append({
                "id": model_name,
                "name": f"{model_name.replace('_', ' ').title()} [Model .pth]",
                "type": "pth_model",
                "pth_path": str(pth),
                "index_path": index_path,
                "size_mb": round(pth.stat().st_size / (1024 * 1024), 2)
            })

        # 2. Quét các file giọng trích xuất từ Clip / URL
        wav_files = list(self.extracted_dir.glob("*.wav")) + list(self.models_dir.glob("*.wav"))
        wav_files = [w for w in wav_files if not w.name.startswith("temp_")]
        
        for wav in wav_files:
            voice_id = f"clip_{wav.stem}"
            models.append({
                "id": voice_id,
                "name": f"🎬 {wav.stem.replace('_', ' ').title()} [Từ Clip/URL]",
                "type": "clip_voice",
                "wav_path": str(wav),
                "audio_url": f"/api/audio-extracted/{wav.name}",
                "size_mb": round(wav.stat().st_size / (1024 * 1024), 2)
            })

        return models

    def extract_voice_from_clip(self, input_media_path: str, output_name: str) -> Dict[str, any]:
        """
        Trích xuất âm thanh từ file video hoặc audio clip bằng FFmpeg.
        Áp dụng bộ lọc chống ồn và chuẩn hóa âm lượng.
        """
        ffmpeg_exe = self._get_ffmpeg_exe()

        safe_name = "".join(c for c in output_name if c.isalnum() or c in ("-", "_")).strip()
        if not safe_name:
            safe_name = f"giong_clip_{uuid.uuid4().hex[:6]}"

        output_wav = self.extracted_dir / f"{safe_name}.wav"

        # Lệnh FFmpeg trích xuất âm thanh mono 44.1kHz, lọc bỏ tạp âm trầm & xì chói
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
            # Fallback không dùng filter nếu gặp lỗi codec
            fb_cmd = [
                ffmpeg_exe, "-y", "-i", str(input_media_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
                str(output_wav)
            ]
            fb_res = subprocess.run(fb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if fb_res.returncode != 0:
                raise RuntimeError(f"Không thể trích xuất âm thanh từ clip: {fb_res.stderr}")

        size_kb = round(output_wav.stat().st_size / 1024, 1)
        return {
            "id": f"clip_{safe_name}",
            "filename": output_wav.name,
            "path": str(output_wav),
            "size_kb": size_kb,
            "url": f"/api/audio-extracted/{output_wav.name}"
        }

    def extract_voice_from_url(self, url: str, voice_name: str, uploads_dir: Path) -> Dict[str, any]:
        """
        Tải video/audio từ đường link (TikTok, YouTube, Shorts, Facebook...) qua yt-dlp
        và tự động trích xuất giọng nói.
        """
        import yt_dlp

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
            'max_filesize': 50 * 1024 * 1024, # Tối đa 50MB
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[yt-dlp] Đang tải audio từ link: {url}")
            ydl.download([url])

        if not expected_output.exists():
            # Tìm file audio được tải về
            candidates = list(uploads_dir.glob(f"yt_{temp_id}.*"))
            if not candidates:
                raise RuntimeError("Không thể tải âm thanh từ đường link đã cung cấp.")
            source_file = candidates[0]
        else:
            source_file = expected_output

        try:
            # Dùng extract_voice_from_clip để lọc ồn và chuyển thành profile chuẩn
            res = self.extract_voice_from_clip(str(source_file), voice_name)
            return res
        finally:
            # Dọn dẹp file tải tạm
            for f in uploads_dir.glob(f"yt_{temp_id}.*"):
                try:
                    f.unlink()
                except Exception:
                    pass

    def concat_audio_segments(self, audio_files: List[str], output_file: str) -> bool:
        """
        Ghép nối nhiều đoạn âm thanh đối thoại thành 1 file hoàn chỉnh bằng FFmpeg.
        """
        if not audio_files:
            return False
        if len(audio_files) == 1:
            import shutil
            shutil.copyfile(audio_files[0], output_file)
            return True

        ffmpeg_exe = self._get_ffmpeg_exe()
        list_file = Path(output_file).parent / f"concat_{uuid.uuid4().hex[:6]}.txt"
        
        try:
            with open(list_file, "w", encoding="utf-8") as f:
                for a in audio_files:
                    # Đường dẫn file cho FFmpeg concat
                    safe_path = str(Path(a).resolve()).replace("\\", "/")
                    f.write(f"file '{safe_path}'\n")

            cmd = [
                ffmpeg_exe,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(output_file)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                # Thử lại với re-encode nếu khác codec
                rec_cmd = [
                    ffmpeg_exe, "-y", "-f", "concat", "-safe", "0",
                    "-i", str(list_file),
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    str(output_file)
                ]
                subprocess.run(rec_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            return True
        except Exception as e:
            print(f"[Lỗi ghép audio] {e}")
            return False
        finally:
            if list_file.exists():
                try:
                    list_file.unlink()
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
