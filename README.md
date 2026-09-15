# Viet Voice Studio 🎙️
### Công cụ Đọc Văn Bản & Nhân Bản Giọng Nói Tiếng Việt 1-Click

Viet Voice Studio là giải pháp mã nguồn mở, **hoàn toàn miễn phí & không giới hạn ký tự**, giúp bạn tạo giọng đọc tiếng Việt tự nhiên và nhân bản giọng nói cá nhân chỉ từ 1 đoạn video clip ngắn.

---

## ✨ Tính Năng Nổi Bật

* **🎬 Đưa Clip vào lấy giọng (Voice Extraction):** Tải lên bất kỳ video clip nào (TikTok, YouTube, MP4, MOV, MKV...) hoặc file ghi âm. AI sẽ tự động tách lời nói, lọc tạp âm và tạo profile giọng của bạn trong 3 giây.
* **⚡ 1-Click Chạy Ngay (`run.bat`):** Chỉ cần click đúp chuột trên Windows là tool tự động khởi chạy và mở trình duyệt web.
* **💎 Ngắt nghỉ tự nhiên theo ngữ điệu 3 miền:** Xử lý tự động dấu chấm, dấu phẩy, ngắt dòng để lấy hơi như người thật. Hỗ trợ chèn các thẻ ngắt nghỉ tùy ý: `[nghỉ 0.5s]`, `[nghỉ 1s]`, `[nghỉ 2s]`.
* **💯 Hoàn toàn Miễn phí & Không giới hạn:** Đọc bao nhiêu văn bản tùy ý mà không phải trả phí API hay lo hết hạn ngạch.
* **💜 Hỗ trợ Model cá nhân:** Nạp trực tiếp file model `.pth` (RVC v2) để sử dụng trọn đời.

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy

### Cách 1: Chạy trên Windows (1-Click)
1. Clone hoặc tải source code về máy:
   ```bash
   git clone https://github.com/luckyluong2k-collab/voice.git
   cd voice
   ```
2. Click đúp chuột vào file **`run.bat`**.
3. Trình duyệt sẽ tự động mở giao diện tại `http://127.0.0.1:7860`.

### Cách 2: Chạy bằng lệnh Python
```bash
# Cài đặt thư viện
pip install -r requirements.txt

# Khởi chạy server
python app.py
```

### Cách 3: Chạy bằng Docker
```bash
docker build -t viet-voice-studio .
docker run -d -p 7860:7860 viet-voice-studio
```

---

## 📖 Hướng Dẫn Sử Dụng

1. **Đưa Clip vào lấy giọng:**
   * Tại cột bên phải, kéo thả clip video của bạn vào ô **"Đưa Clip vào lấy giọng"**.
   * Bấm **"TÁCH VÀ LẤY GIỌNG TỪ CLIP NÀY"**.
   * Sau 2–3 giây, đoạn giọng sẽ được trích xuất và tự động nạp vào danh sách giọng đọc của bạn.
2. **Tạo giọng nói:**
   * Dán văn bản tiếng Việt vào ô nhập liệu.
   * Chọn giọng đọc (Nam Minh, Hoài My hoặc Giọng trích xuất từ clip).
   * Bấm **TẠO GIỌNG NÓI NGAY** (`Ctrl + Enter`).
   * Nghe trực tiếp và bấm **TẢI FILE .MP3**.

---

## 📂 Cấu Trúc Thư Mục

```
voice/
├── app.py                  # FastAPI backend server
├── voice_converter.py      # Module xử lý âm thanh & trích xuất giọng bằng FFmpeg
├── requirements.txt        # Danh sách thư viện phụ thuộc
├── run.bat                 # File khởi động 1-click cho Windows
├── Dockerfile              # Cấu hình container Docker
├── models/                 # Thư mục chứa model .pth & giọng trích xuất
│   └── extracted_voices/   # Giọng bóc tách từ video clip
├── outputs/                # File âm thanh xuất ra (.mp3)
├── web/
│   └── index.html          # Giao diện Web hiện đại (Dark/Light mode)
└── README.md
```

---

## 🤝 Đóng Góp & Phát Triển
Mọi đóng góp và pull request đều được hoan nghênh tại [luckyluong2k-collab/voice](https://github.com/luckyluong2k-collab/voice).
