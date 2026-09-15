# HƯỚNG DẪN THU ÂM & NẠP GIỌNG CỦA BẠN (CHỈ LÀM 1 LẦN DUY NHẤT)

Chào bạn, để AI học được chính xác **90–95% âm sắc, độ trầm bổng và phương ngữ 3 miền (Bắc/Trung/Nam)** của bạn, bạn chỉ cần làm theo 3 bước sau:

---

### BƯỚC 1: Thu âm giọng nói của bạn (5 – 10 phút)
1. **Thiết bị:** Dùng điện thoại (ứng dụng "Ghi âm" có sẵn trên iPhone / Android) hoặc tai nghe có mic cắm máy tính.
2. **Không gian:** Ngồi trong phòng kín, yên tĩnh (không bật quạt chĩa thẳng vào mic, hạn chế tiếng xe cộ).
3. **Cách đọc:**
   - Mở 1 bài báo, một mẩu truyện ngắn hoặc sách bạn thích.
   - Đọc tự nhiên với đúng chất giọng hàng ngày của bạn (nói rõ chữ, giữ nhịp thở bình thường).
   - Độ dài: Khoảng 5 đến 10 phút là lý tưởng nhất.
4. **Xuất file:** Lưu file thu âm dưới định dạng `.wav` hoặc `.mp3` (ví dụ: `giong_cua_toi.wav`).

---

### BƯỚC 2: Tạo file Model giọng (.pth) trên Google Colab Free (10–15 phút)
*(Google Colab cấp miễn phí card đồ họa GPU T4 16GB để bạn huấn luyện mô hình mà không làm nóng máy tính của bạn)*

1. Mở notebook Google Colab RVC v2 (miễn phí):
   - Link: https://colab.research.google.com/github/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/main/RVC_v2_Colab.ipynb
2. Nhấn nút **Connect** (Kết nối GPU T4).
3. Bấm chạy các ô lệnh tuần tự (hoặc Runtime -> Run all).
4. Khi giao diện WebUI RVC hiện ra:
   - Vào tab **Train**.
   - Đặt tên model (ví dụ: `giong_anh_tuan`).
   - Tải file ghi âm `giong_cua_toi.wav` lên.
   - Nhấn **Process Data** -> **Feature Extraction** -> **Train Model**.
5. Sau khi train xong, tải về 2 file:
   - `giong_anh_tuan.pth` (khoảng 50MB)
   - `giong_anh_tuan.index` (khoảng 2MB, nếu có)

---

### BƯỚC 3: Nạp vào Tool để dùng trọn đời
1. Copy file `.pth` và `.index` bỏ vào thư mục:
   ```
   C:\Users\ADMIN\.gemini\antigravity\scratch\viet_voice_clone\models\
   ```
   *(Hoặc bạn chỉ cần kéo thả file đó vào ô "Nạp file giọng của bạn" ngay trên giao diện web của Tool).*
2. Trên giao diện Tool, bấm nút **Làm mới**, sau đó chọn **Giọng của tôi: ...** từ danh sách.
3. Từ nay về sau, mỗi ngày bạn chỉ cần dán văn bản vào và bấm **Tạo giọng nói ngay**!
