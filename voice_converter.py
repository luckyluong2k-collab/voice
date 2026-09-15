import os
import re
import json
import uuid
import math
import wave
import array
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

    def extract_acoustic_profile(self, audio_path: str) -> dict:
        """
        Trích xuất đặc trưng âm học: cao độ trung vị (F0), giới tính,
        tỉ lệ dịch tông (pitch_ratio) và bộ lọc formant/EQ tương ứng với giọng mẫu.
        """
        ffmpeg_exe = self._get_ffmpeg_exe()
        temp_wav = self.models_dir / f"temp_prof_{uuid.uuid4().hex[:6]}.wav"
        
        try:
            # Chuyển đổi mẫu 30s về 22050Hz mono 16-bit PCM để xử lý nhanh và chính xác
            cmd = [
                ffmpeg_exe, "-y",
                "-i", str(audio_path),
                "-t", "30",
                "-ar", "22050",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                str(temp_wav)
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if not temp_wav.exists() or temp_wav.stat().st_size < 1000:
                return self._default_profile()

            with wave.open(str(temp_wav), 'rb') as wf:
                rate = wf.getframerate()
                raw_bytes = wf.readframes(wf.getnframes())
                samples_all = array.array('h', raw_bytes)

            # 1. Đo Pitch F0 bằng Autocorrelation tối ưu hóa
            down = 5
            sub_rate = rate // down
            sub_samples = samples_all[::down]
            frame_len = int(sub_rate * 0.04) # 40ms
            step = int(sub_rate * 0.02)      # 20ms
            min_lag = int(sub_rate / 350)    # Tối đa 350Hz
            max_lag = int(sub_rate / 70)     # Tối thiểu 70Hz

            pitches = []
            for i in range(0, len(sub_samples) - frame_len, step):
                f = sub_samples[i:i+frame_len]
                c0 = sum(x*x for x in f)
                if c0 < 300000:
                    continue
                best_c, best_l = -1, 0
                for l in range(min_lag, max_lag):
                    c = sum(f[k]*f[k+l] for k in range(frame_len - l))
                    if c > best_c:
                        best_c = c
                        best_l = l
                if best_c > 0.40 * c0 and best_l > 0:
                    p = sub_rate / best_l
                    if 70 <= p <= 350:
                        pitches.append(p)

            pitches.sort()
            med_f0 = round(pitches[len(pitches)//2], 1) if pitches else 125.0

            # Phân loại giọng nam / nữ dựa trên cao độ F0
            gender = "male" if med_f0 < 165 else "female"
            base_voice = "vi-VN-NamMinhNeural" if gender == "male" else "vi-VN-HoaiMyNeural"
            base_f0 = 141.3 if gender == "male" else 215.0
            pitch_ratio = round(med_f0 / base_f0, 4)

            # 2. Đo phân bố phổ âm thanh để tái tạo Formant / Timbre
            bands = [
                (110, 60, 150),
                (220, 150, 300),
                (450, 300, 600),
                (850, 600, 1200),
                (1600, 1200, 2400),
                (3500, 2400, 4800),
                (6500, 4800, 10000)
            ]
            ref_spec = [0.109, 0.467, 0.389, 0.014, 0.005, 0.005, 0.010] if gender == "male" else [0.04, 0.30, 0.45, 0.12, 0.05, 0.025, 0.015]

            N = 512
            band_e = [0.0] * len(bands)
            step_s = rate // 2
            for pos in range(0, len(samples_all) - N, step_s):
                chunk = samples_all[pos:pos+N]
                rms = math.sqrt(sum(s*s for s in chunk) / N)
                if rms < 1500:
                    continue
                for b_idx, (fc, fl, fh) in enumerate(bands):
                    k_low = int(fl * N / rate)
                    k_high = int(fh * N / rate)
                    be = 0.0
                    for k in range(k_low, k_high + 1, max(1, (k_high - k_low) // 4)):
                        re = sum(chunk[n] * math.cos(2 * math.pi * k * n / N) for n in range(0, N, 8))
                        im = sum(chunk[n] * math.sin(2 * math.pi * k * n / N) for n in range(0, N, 8))
                        be += re*re + im*im
                    band_e[b_idx] += be

            tot = sum(band_e) or 1.0
            u_spec = [e / tot for e in band_e]

            eq_filters = []
            for (fc, fl, fh), u_val, r_val in zip(bands, u_spec, ref_spec):
                if r_val > 0 and u_val > 0:
                    diff_db = 10 * math.log10(u_val / r_val)
                    diff_db = max(-6.0, min(6.0, diff_db))
                    if abs(diff_db) >= 1.0:
                        eq_filters.append(f"equalizer=f={fc}:t=q:w=1.4:g={diff_db:.1f}")

            return {
                "f0": med_f0,
                "gender": gender,
                "base_voice": base_voice,
                "pitch_ratio": pitch_ratio,
                "eq_filters": eq_filters,
                # Lưu phổ trung bình của chính file mẫu để hiệu chỉnh theo
                # giọng nền thực tế, thay vì so với một phổ nam/nữ chung.
                "spectrum_bands": [[fc, fl, fh] for fc, fl, fh in bands],
                "spectral_profile": [round(value, 8) for value in u_spec]
            }
        except Exception as e:
            print(f"[Lỗi trích xuất profile âm học] {e}")
            return self._default_profile()
        finally:
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception:
                    pass

    def _default_profile(self) -> dict:
        return {
            "f0": 125.0,
            "gender": "male",
            "base_voice": "vi-VN-NamMinhNeural",
            "pitch_ratio": 0.88,
            "eq_filters": [
                "equalizer=f=115:t=q:w=1.2:g=2.0",
                "equalizer=f=850:t=q:w=1.4:g=4.0"
            ]
        }

    def list_models(self) -> List[Dict[str, any]]:
        """
        Quét danh sách các model và giọng cá nhân đã nạp, kèm thông số âm học F0/Gender
        """
        models = []
        meta = self._load_metadata()
        meta_changed = False

        # 1. Quét model .pth (RVC)
        pth_files = list(self.models_dir.glob("*.pth"))
        for pth in pth_files:
            model_name = pth.stem
            index_files = list(self.models_dir.glob(f"{model_name}*.index"))
            index_path = str(index_files[0]) if index_files else None
            
            voice_meta = meta.get(model_name, {})
            custom_name = voice_meta.get("custom_name")
            display_name = custom_name if custom_name else f"{model_name.replace('_', ' ').title()}"

            models.append({
                "id": model_name,
                "name": display_name,
                "type": "pth_model",
                "tag": "Model .pth RVC",
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

            # Tự động phân tích profile âm học nếu chưa lưu
            profile = voice_meta.get("profile")
            if not profile or "f0" not in profile or "spectral_profile" not in profile:
                profile = self.extract_acoustic_profile(str(wav))
                voice_meta["profile"] = profile
                voice_meta["custom_name"] = display_name
                voice_meta["filename"] = wav.name
                meta[voice_id] = voice_meta
                meta_changed = True

            f0 = profile.get("f0", 120)
            gender_vn = "Giọng Nam" if profile.get("gender") == "male" else "Giọng Nữ"
            tag_label = f"{gender_vn} ({f0:.0f}Hz)"

            models.append({
                "id": voice_id,
                "name": display_name,
                "filename": wav.name,
                "type": "clip_voice",
                "tag": tag_label,
                "f0": f0,
                "gender": profile.get("gender", "male"),
                "base_voice": profile.get("base_voice", "vi-VN-NamMinhNeural"),
                "profile": profile,
                "wav_path": str(wav),
                "audio_url": f"/api/audio-extracted/{wav.name}",
                "size_mb": round(wav.stat().st_size / (1024 * 1024), 2),
                "time": datetime.fromtimestamp(wav.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            })

        if meta_changed:
            self._save_metadata(meta)

        return models

    def get_model_info(self, model_id: str) -> Optional[Dict[str, any]]:
        for m in self.list_models():
            if m["id"] == model_id:
                return m
        return None

    def extract_voice_from_clip(self, input_media_path: str, output_name: str) -> Dict[str, any]:
        ffmpeg_exe = self._get_ffmpeg_exe()

        display_name = output_name.strip() if output_name and output_name.strip() else "Giọng Trích Xuất"
        
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

        # Trích xuất đặc trưng âm học (Pitch F0 & Formants)
        profile = self.extract_acoustic_profile(str(output_wav))

        voice_id = f"clip_{safe_name}"
        meta = self._load_metadata()
        meta[voice_id] = {
            "custom_name": display_name,
            "filename": output_wav.name,
            "created_at": datetime.now().isoformat(),
            "profile": profile
        }
        self._save_metadata(meta)

        size_kb = round(output_wav.stat().st_size / 1024, 1)
        gender_vn = "Giọng Nam" if profile.get("gender") == "male" else "Giọng Nữ"
        return {
            "id": voice_id,
            "name": display_name,
            "filename": output_wav.name,
            "path": str(output_wav),
            "size_kb": size_kb,
            "f0": profile.get("f0"),
            "gender": profile.get("gender"),
            "tag": f"{gender_vn} ({profile.get('f0', 0):.0f}Hz)",
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
        """
        Thực hiện chuyển đổi âm sắc và cao độ F0 sang giọng cá nhân người dùng:
        1. Sử dụng Rubberband Filter chất lượng cao để dịch chuyển chính xác cao độ F0
        2. Áp dụng chuỗi Equalizer Formant thích ứng theo đặc trưng khoang miệng/cổ họng của giọng mẫu
        3. Tái chuẩn hóa âm lượng chuẩn phát thanh Loudnorm (EBU R128)
        """
        model_info = self.get_model_info(model_id)
        if not model_info:
            print(f"[apply_voice_conversion] Không tìm thấy model {model_id}")
            return False

        profile = model_info.get("profile")
        if not profile:
            wav_path = model_info.get("wav_path")
            if wav_path and os.path.exists(wav_path):
                profile = self.extract_acoustic_profile(wav_path)
            else:
                profile = self._default_profile()

        ffmpeg_exe = self._get_ffmpeg_exe()

        base_ratio = profile.get("pitch_ratio", 1.0)
        user_mult = 1.0 + (pitch_shift / 100.0)
        total_pitch_scale = round(base_ratio * user_mult, 4)
        total_pitch_scale = max(0.55, min(1.85, total_pitch_scale))

        eq_filters = profile.get("eq_filters", [])
        if not eq_filters:
            eq_filters = [
                "equalizer=f=115:t=q:w=1.2:g=2.5",
                "equalizer=f=850:t=q:w=1.4:g=5.0",
                "equalizer=f=3500:t=q:w=1.2:g=-2.5"
            ]

        # Hiệu chỉnh phổ động: so sánh file TTS nền vừa tạo với phổ trung
        # bình của file người dùng. Cách này bám vào đúng giọng nền đang dùng
        # và tránh phụ thuộc hoàn toàn vào các mức EQ mặc định.
        target_spectrum = profile.get("spectral_profile")
        spectrum_bands = profile.get("spectrum_bands")
        if target_spectrum and spectrum_bands:
            try:
                source_profile = self.extract_acoustic_profile(input_wav)
                source_spectrum = source_profile.get("spectral_profile")
                if source_spectrum and len(source_spectrum) == len(target_spectrum):
                    calibrated_eq = []
                    for band, target_value, source_value in zip(
                        spectrum_bands, target_spectrum, source_spectrum
                    ):
                        if target_value > 0 and source_value > 0:
                            gain = 10 * math.log10(target_value / source_value)
                            gain = max(-6.0, min(6.0, gain))
                            if abs(gain) >= 0.8:
                                calibrated_eq.append(
                                    f"equalizer=f={band[0]}:t=q:w=1.4:g={gain:.1f}"
                                )
                    if calibrated_eq:
                        eq_filters = calibrated_eq
            except Exception as exc:
                print(f"[Voice Conversion] Bỏ qua hiệu chỉnh phổ động: {exc}")

        af_list = [
            f"rubberband=pitch={total_pitch_scale:.4f}:formant=shifted:pitchq=quality"
        ]
        af_list.extend(eq_filters)
        af_list.append("loudnorm=I=-16:TP=-1.5:LRA=11")

        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(input_wav),
            "-af", ",".join(af_list),
            str(output_wav)
        ]

        print(f"[Voice Conversion] Đang chuyển đổi giọng sang {model_info['name']} (Scale: {total_pitch_scale:.4f}, Filters: {len(eq_filters)} EQs)...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if res.returncode == 0 and Path(output_wav).exists() and Path(output_wav).stat().st_size > 1000:
            print(f"[Voice Conversion] Chuyển đổi thành công: {output_wav}")
            # Hiệu chỉnh lần cuối theo F0 thực đo của file đầu ra. F0 của
            # Edge-TTS thay đổi theo câu, nên dùng một base_f0 cố định dễ bị
            # lệch vài phần trăm so với giọng mẫu người dùng.
            target_f0 = float(profile.get("f0") or 0)
            if target_f0 > 70:
                try:
                    measured = self.extract_acoustic_profile(str(output_wav)).get("f0")
                    measured_f0 = float(measured or 0)
                    correction = target_f0 / measured_f0 if measured_f0 > 70 else 1.0
                    if 0.96 > correction or correction > 1.04:
                        correction = max(0.85, min(1.18, correction))
                        corrected_path = Path(output_wav).with_name(
                            f"{Path(output_wav).stem}_pitchfix{Path(output_wav).suffix}"
                        )
                        fix_cmd = [
                            ffmpeg_exe, "-y",
                            "-i", str(output_wav),
                            "-af", f"rubberband=pitch={correction:.4f}:tempo=1:formant=preserved:pitchq=quality",
                            str(corrected_path)
                        ]
                        fix_res = subprocess.run(
                            fix_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                        )
                        if fix_res.returncode == 0 and corrected_path.exists() and corrected_path.stat().st_size > 1000:
                            corrected_path.replace(output_wav)
                            print(
                                f"[Voice Conversion] Hiệu chỉnh F0 {measured_f0:.1f}Hz -> "
                                f"{target_f0:.1f}Hz (x{correction:.4f})"
                            )
                except Exception as exc:
                    # Không làm hỏng file đã chuyển đổi chỉ vì bước tinh chỉnh.
                    print(f"[Voice Conversion] Bỏ qua hiệu chỉnh F0: {exc}")
            return True

        print(f"[Voice Conversion] Rubberband thất bại ({res.stderr[:200]}), đang kích hoạt bộ lọc thay thế asetrate/atempo...")
        orig_rate = 44100
        new_rate = int(orig_rate * total_pitch_scale)
        tempo = round(1.0 / total_pitch_scale, 4)
        fb_filters = [
            f"asetrate={new_rate}",
            f"atempo={tempo}",
            f"aresample={orig_rate}"
        ] + eq_filters + ["loudnorm=I=-16:TP=-1.5:LRA=11"]

        fb_cmd = [
            ffmpeg_exe, "-y",
            "-i", str(input_wav),
            "-af", ",".join(fb_filters),
            str(output_wav)
        ]
        fb_res = subprocess.run(fb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return fb_res.returncode == 0 and Path(output_wav).exists()
