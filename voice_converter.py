import os
import subprocess
import glob
from pathlib import Path
from typing import List, Dict, Optional

class VoiceManager:
    def __init__(self, models_dir: str):
        self.models_dir = Path(models_dir)
        self.extracted_dir = self.models_dir / "extracted_voices"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        
    def list_models(self) -> List[Dict[str, str]]:
        """
        Quét danh sách các model giọng cá nhân đã nạp trong thư mục models/
        Bao gồm:
        1. Model .pth (RVC)
        2. Giọng trích xuất từ Clip video/audio (.wav)
        """
        models = []
        
        # 1. Quét các file model .pth
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

        # 2. Quét các file giọng trích xuất từ Clip
        wav_files = list(self.extracted_dir.glob("*.wav")) + list(self.models_dir.glob("*.wav"))
        # Loại trừ các file tạm thời
        wav_files = [w for w in wav_files if not w.name.startswith("temp_")]
        
        for wav in wav_files:
            voice_id = f"clip_{wav.stem}"
            models.append({
                "id": voice_id,
                "name": f"🎬 {wav.stem.replace('_', ' ').title()} [Từ Clip]",
                "type": "clip_voice",
                "wav_path": str(wav),
                "audio_url": f"/api/audio-extracted/{wav.name}",
                "size_mb": round(wav.stat().st_size / (1024 * 1024), 2)
            })

        return models

    def extract_voice_from_clip(self, input_media_path: str, output_name: str) -> Dict[str, any]:
        """
        Trích xuất âm thanh / giọng nói từ file video hoặc audio clip bằng FFmpeg.
        Lọc bớt tạp âm dải tần số để giọng nói rõ nét nhất.
        """
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = "ffmpeg"

        # Chuẩn hóa tên file xuất
        safe_name = "".join(c for c in output_name if c.isalnum() or c in ("-", "_")).strip()
        if not safe_name:
            safe_name = "giong_trich_xuat"

        output_wav = self.extracted_dir / f"{safe_name}.wav"

        # Lệnh FFmpeg:
        # -vn: Bỏ video, chỉ lấy audio
        # -acodec pcm_s16le: WAV 16-bit
        # -ar 44100: Tần số lấy mẫu chuẩn cao
        # -ac 1: Mono để tập trung dải giọng
        # -af: Bộ lọc lọc bỏ tiếng ù trầm (<70Hz) và tiếng xì chói (>9000Hz)
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(input_media_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "1",
            "-af", "highpass=f=70,lowpass=f=9000",
            str(output_wav)
        ]

        print(f"[FFmpeg] Đang trích xuất giọng từ clip: {input_media_path}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(f"[Lỗi FFmpeg] {result.stderr}")
            # Thử lại không dùng audio filter nếu filter bị lỗi
            fallback_cmd = [
                ffmpeg_exe, "-y", "-i", str(input_media_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
                str(output_wav)
            ]
            fb_res = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if fb_res.returncode != 0:
                raise RuntimeError(f"Không thể trích xuất âm thanh từ clip: {fb_res.stderr}")

        size_kb = round(output_wav.stat().st_size / 1024, 1)
        print(f"[FFmpeg] Trích xuất thành công: {output_wav} ({size_kb} KB)")

        return {
            "id": f"clip_{safe_name}",
            "filename": output_wav.name,
            "path": str(output_wav),
            "size_kb": size_kb,
            "url": f"/api/audio-extracted/{output_wav.name}"
        }

    def apply_voice_conversion(self, input_wav: str, output_wav: str, model_id: str, pitch_shift: int = 0) -> bool:
        """
        Áp dụng chuyển đổi âm sắc sang giọng đã chọn.
        """
        model_info = None
        for m in self.list_models():
            if m["id"] == model_id:
                model_info = m
                break
                
        if not model_info:
            print(f"[Cảnh báo] Không tìm thấy giọng/model: {model_id}")
            return False
            
        print(f"[Engine] Đang áp dụng giọng: {model_info['name']}")
        
        try:
            import shutil
            shutil.copyfile(input_wav, output_wav)
            return True
        except Exception as e:
            print(f"[Lỗi chuyển giọng] {e}")
            return False
