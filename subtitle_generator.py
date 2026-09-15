import re
from datetime import timedelta
from typing import List, Dict, Optional
import edge_tts

class SubtitleGenerator:
    def __init__(self):
        self.submaker = edge_tts.SubMaker()

    def feed(self, chunk: dict):
        if chunk.get("type") in ("WordBoundary", "SentenceBoundary"):
            try:
                self.submaker.feed(chunk)
            except Exception as e:
                pass

    def get_srt(self) -> str:
        """
        Lấy nội dung phụ đề chuẩn định dạng .SRT
        """
        try:
            srt_content = self.submaker.get_srt()
            if not srt_content or not srt_content.strip():
                return ""
            return srt_content
        except Exception as e:
            print(f"[Lỗi SubMaker] {e}")
            return ""

    def save_srt(self, file_path: str) -> bool:
        srt_text = self.get_srt()
        if not srt_text:
            return False
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(srt_text)
        return True
