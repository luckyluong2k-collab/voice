import urllib.request
import json
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:7860"

def test_api():
    print("[1] Testing /api/health...")
    req = urllib.request.urlopen(f"{BASE_URL}/api/health")
    data = json.loads(req.read().decode("utf-8"))
    assert data["status"] == "ok"
    print(" -> Health check PASSED!")

    print("[2] Testing /api/voices...")
    req = urllib.request.urlopen(f"{BASE_URL}/api/voices")
    data = json.loads(req.read().decode("utf-8"))
    assert len(data) >= 2
    print(f" -> Found {len(data)} base voices: {[v['name'] for v in data]}")

    print("[3] Testing / (index.html)...")
    req = urllib.request.urlopen(f"{BASE_URL}/")
    html = req.read().decode("utf-8")
    assert "Viet Voice Studio" in html
    print(" -> Web UI index.html loaded successfully!")

    print("[4] Testing /api/tts (Generating Vietnamese speech)...")
    payload = json.dumps({
        "text": "Xin chào, đây là hệ thống nhân bản giọng nói và đọc văn bản tiếng Việt tự động. [nghỉ 0.5s] Âm thanh ngắt nghỉ rất tự nhiên!",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "pause_style": "natural"
    }).encode("utf-8")

    tts_req = urllib.request.Request(
        f"{BASE_URL}/api/tts",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(tts_req)
    tts_data = json.loads(res.read().decode("utf-8"))
    assert tts_data["status"] == "success"
    audio_url = tts_data["audio_url"]
    print(f" -> TTS PASSED! Audio URL: {audio_url}, Stats: {tts_data['stats']}")

    print("[5] Verifying audio file download...")
    audio_req = urllib.request.urlopen(f"{BASE_URL}{audio_url}")
    audio_bytes = audio_req.read()
    assert len(audio_bytes) > 5000
    print(f" -> Audio downloaded successfully! Size: {len(audio_bytes)} bytes")

    print("[6] Testing /api/history...")
    hist_req = urllib.request.urlopen(f"{BASE_URL}/api/history")
    hist_data = json.loads(hist_req.read().decode("utf-8"))
    assert len(hist_data) >= 1
    print(f" -> History retrieved: {len(hist_data)} audio files found.")

    print("\n>>> ALL TESTS PASSED SUCCESSFULLY 100%! <<<")

if __name__ == "__main__":
    test_api()
