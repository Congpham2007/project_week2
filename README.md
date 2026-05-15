# 🍔 Smart Foodie App - Hệ thống Gợi ý Món ăn thông minh

Dự án này là một ứng dụng Full-Stack tích hợp **Fuzzy Logic (Logic Mờ)** để gợi ý món ăn, lập kế hoạch thực đơn tự động và vẽ bản đồ di chuyển đến các quán ăn/nhà hàng. 

Ứng dụng có giao diện giả lập Mobile đẹp mắt được viết bằng **HTML/TailwindCSS** và hệ thống Backend mạnh mẽ viết bằng **Python (Flask)**.

---

## 🌟 Các Tính Năng Nổi Bật

1. **Gợi ý món ăn thông minh (Fuzzy Logic):** Dựa vào Mức độ đói, Ngân sách, và Thời gian rảnh để tính toán phần trăm (%) độ phù hợp của từng món ăn.
2. **Kế hoạch tự động (Meal Planner):** Lên thực đơn tự động Sáng - Trưa - Tối đảm bảo cân bằng calo.
3. **Bản đồ trực quan (Folium Map):** Tự động vẽ lộ trình và trạm dừng (các quán ăn) kèm theo thông tin chi tiết trên bản đồ động.
4. **Thời tiết thời gian thực:** Gọi API OpenWeather để lấy thời tiết và gợi ý loại món ăn phù hợp với nhiệt độ hiện tại.

---

## 🚀 Hướng Dẫn Cài Đặt (Cho người dùng mới)

Để chạy dự án này trên máy của bạn, hãy thực hiện theo các bước sau:

### Bước 1: Clone dự án về máy
Mở Terminal/Command Prompt và chạy lệnh:
```bash
git clone https://github.com/NaughMilk/PDTC-AI-FOOD.git
cd PDTC-AI-FOOD
```

### Bước 2: Tạo Môi trường Ảo (Tùy chọn nhưng khuyên dùng)
Tạo môi trường ảo để các thư viện không bị xung đột với các project khác trong máy:
```bash
python -m venv venv

# Kích hoạt trên Windows:
venv\Scripts\activate

# Kích hoạt trên Mac/Linux:
source venv/bin/activate
```

### Bước 3: Cài đặt các thư viện cần thiết
```bash
pip install -r requirements.txt
```

### Bước 4: Cấu hình API Key (Quan trọng)
Dự án sử dụng API thời tiết thực. Bạn cần tạo một file tên là `.env` ở thư mục gốc của dự án (cùng cấp với `smart_food_logic.py`).
Bên trong file `.env`, hãy dán nội dung sau:
```env
OPENWEATHER_API_KEY=your_api_key_here
```

### Bước 5: Chạy Máy Chủ Backend
Khởi động ứng dụng bằng lệnh:
```bash
python smart_food_logic.py
```
*(Nếu bạn dùng Windows PowerShell và gặp lỗi hiển thị font tiếng Việt ở console, hãy chạy: `$env:PYTHONIOENCODING="utf-8"; python smart_food_logic.py`)*

### Bước 6: Trải nghiệm Ứng dụng
Mở trình duyệt web của bạn và truy cập vào địa chỉ:
👉 **http://localhost:5000**

---

## 🛠️ Tech Stack
- **Frontend:** HTML, JavaScript, TailwindCSS
- **Backend:** Python, Flask
- **AI/Thuật toán:** `scikit-fuzzy`, `numpy`
- **Bản đồ:** `folium`

---
*Dự án thuộc Bài Tập Lớn môn học - Nhóm PDTC*
