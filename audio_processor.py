import os
import re
import math
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
import imageio_ffmpeg

class AudioProcessor:
    def __init__(self):
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    def generate_breath_sample(self, output_path: str, duration: float = 0.22, volume: float = 0.16) -> bool:
        """
        Tao mau am thanh tieng lay hoi (hit vao) tu nhien bang bo loc dai tan thanh quan nguoi.
        """
        fade_in = max(0.04, duration * 0.3)
        fade_out = max(0.05, duration * 0.4)
        fade_out_start = max(0.01, duration - fade_out)
        
        filter_str = (
            f"anoisesrc=d={duration:.2f}:c=pink:r=44100,"
            f"highpass=f=380,lowpass=f=2300,"
            f"afade=t=in:ss=0:d={fade_in:.2f},"
            f"afade=t=out:st={fade_out_start:.2f}:d={fade_out:.2f},"
            f"volume={volume:.2f}"
        )
        cmd = [
            self.ffmpeg, "-y", "-f", "lavfi",
            "-i", filter_str,
            str(output_path)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return res.returncode == 0

    def detect_pauses(self, audio_path: str, min_silence: float = 0.22, noise_thresh: str = "-28dB") -> List[Tuple[float, float, float]]:
        """
        Phat hien cac khoang ngat nghi trong audio (start_time, end_time, duration).
        """
        cmd = [
            self.ffmpeg, "-i", str(audio_path),
            "-af", f"silencedetect=noise={noise_thresh}:d={min_silence}",
            "-f", "null", "-"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        silences = []
        current_start = None
        for line in res.stderr.splitlines():
            m_s = re.search(r"silence_start:\s*([\d\.]+)", line)
            if m_s:
                current_start = float(m_s.group(1))
            m_e = re.search(r"silence_end:\s*([\d\.]+)\s*\|\s*silence_duration:\s*([\d\.]+)", line)
            if m_e and current_start is not None:
                end_t = float(m_e.group(1))
                dur = float(m_e.group(2))
                silences.append((current_start, end_t, dur))
                current_start = None
        return silences

    def process_voice(
        self,
        input_audio: str,
        output_audio: str,
        pitch_percent: int = 0,
        voice_style: str = "story",
        breath_mode: str = "natural"
    ) -> bool:
        """
        Nang cap chat luong am thanh:
        1. Nhip lay hoi nhu nguoi that (breath_mode)
        2. Tong cao thap (pitch_percent: -20 den +20)
        3. Giong dieu & EQ phong cach (voice_style)
        """
        temp_dir = Path(tempfile.gettempdir()) / "viet_voice_proc"
        temp_dir.mkdir(parents=True, exist_ok=True)
        breath_sample_path = str(temp_dir / f"breath_{breath_mode}.wav")

        # Cau hinh am luong va do dai lay hoi theo che do
        breath_configs = {
            "soft": {"duration": 0.18, "volume": 0.10},
            "natural": {"duration": 0.22, "volume": 0.16},
            "deep": {"duration": 0.28, "volume": 0.22}
        }

        has_breath = breath_mode in breath_configs
        cfg = breath_configs.get(breath_mode, {"duration": 0.22, "volume": 0.16})
        if has_breath:
            self.generate_breath_sample(breath_sample_path, duration=cfg["duration"], volume=cfg["volume"])

        # Phat hien cac khoang lang de chen hoi tho
        breath_delays = []
        if has_breath:
            pauses = self.detect_pauses(input_audio, min_silence=0.26)
            for (p_start, p_end, p_dur) in pauses:
                # Khong chen o sat dau file (< 0.2s)
                if p_start < 0.15:
                    continue
                # Vi tri hit hoi: truoc khi tieng noi tiep theo cat len 0.05s - 0.1s
                breath_time = max(p_start + 0.05, p_end - cfg["duration"] - 0.04)
                breath_delays.append(int(breath_time * 1000))

        # Gioi han toi da 25 diem lay hoi de filter FFmpeg khong qua dai
        if len(breath_delays) > 25:
            breath_delays = breath_delays[:25]

        # Xay dung bo loc tong cao thap (Pitch Shifting)
        # Giu nguyen do dai (tempo bu tru hoan hao)
        pitch_filters = []
        if pitch_percent != 0:
            pitch_percent = max(-25, min(25, pitch_percent))
            factor = 1.0 + (pitch_percent / 100.0)
            target_rate = int(44100 * factor)
            target_tempo = 1.0 / factor
            pitch_filters.append(f"asetrate={target_rate}")
            pitch_filters.append("aresample=44100")
            pitch_filters.append(f"atempo={target_tempo:.4f}")

        # Xay dung bo loc phong cach giong dieu (Voice Style EQ & Dynamics)
        style_filters = []
        if voice_style == "story":  # Ke chuyen / Truyen cam: Tram am, dai dong sau
            style_filters.append("equalizer=f=180:t=q:w=1.2:g=+3.0")
            style_filters.append("equalizer=f=3500:t=q:w=1.0:g=-1.5")
        elif voice_style == "news":  # Tin tuc / Thuyet minh: Trong treo, dut khoat
            style_filters.append("equalizer=f=2600:t=q:w=1.5:g=+2.5")
            style_filters.append("acompressor=threshold=-18dB:ratio=3:attack=5:release=50")
        elif voice_style == "tiktok":  # Soi noi / Review TikTok: Noi bat, bat tai
            style_filters.append("equalizer=f=3200:t=q:w=1.2:g=+3.5")
            style_filters.append("equalizer=f=100:t=q:w=1.0:g=+2.0")
            style_filters.append("acompressor=threshold=-15dB:ratio=4:attack=3:release=40")
        elif voice_style == "podcast":  # Tam su / Podcast: Day tieng, am cung
            style_filters.append("equalizer=f=140:t=q:w=1.5:g=+4.0")
            style_filters.append("equalizer=f=4000:t=q:w=1.0:g=-2.0")

        # Ghep noi filter FFmpeg
        inputs = ["-i", str(input_audio)]
        filter_parts = []
        
        if has_breath and len(breath_delays) > 0:
            for i, delay_ms in enumerate(breath_delays):
                inputs.extend(["-i", breath_sample_path])
                filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[b{i}]")
            
            amix_inputs = "".join([f"[b{i}]" for i in range(len(breath_delays))])
            filter_parts.append(f"[0:a]{amix_inputs}amix=inputs={len(breath_delays)+1}:duration=first:dropout_transition=0[mixed]")
            last_audio = "[mixed]"
        else:
            last_audio = "[0:a]"

        all_post_filters = pitch_filters + style_filters
        if all_post_filters:
            post_chain = ",".join(all_post_filters)
            filter_parts.append(f"{last_audio}{post_chain}[outa]")
            final_map = "[outa]"
        else:
            final_map = last_audio

        if filter_parts:
            filter_complex = ";".join(filter_parts)
            cmd = [
                self.ffmpeg, "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", final_map,
                "-b:a", "192k",
                str(output_audio)
            ]
        else:
            cmd = [
                self.ffmpeg, "-y",
                "-i", str(input_audio),
                "-b:a", "192k",
                str(output_audio)
            ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"[Loi FFmpeg AudioProcessor] {res.stderr}")
            import shutil
            shutil.copyfile(input_audio, output_audio)
            return False
        return True
