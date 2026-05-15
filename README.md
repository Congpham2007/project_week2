# Smart Foodie App

Ứng dụng gợi ý món ăn và lập kế hoạch bữa ăn bằng Fuzzy Logic, kèm thời tiết thực tế, thời gian giao hàng ước tính, và bản đồ gợi ý quán.

Repo hiện tại đã bao gồm:

- `Backend Flask` trong [smart_food_logic.py](./smart_food_logic.py)
- `Frontend HTML` đã được nối vào backend qua các API:
  - `GET /api/weather`
  - `POST /api/recommend`
  - `POST /api/plan`
  - `POST /api/map`

Ứng dụng có thể chạy theo 2 cách:

1. `Khuyến nghị`: chạy Flask tại `http://127.0.0.1:5000`
2. `Tách riêng frontend/backend để debug`: mở HTML bằng static server ở `:4173` và gọi API Flask ở `:5000`

---

## 1. Cấu trúc dự án

Các file quan trọng:

- [smart_food_logic.py](./smart_food_logic.py): backend Flask chính
- [requirements.txt](./requirements.txt): thư viện Python cần cài
- [app.html](./app.html): khung app mobile chính
- [login.html](./login.html): màn hình đăng nhập
- [home.html](./home.html): trang chủ, gọi `weather` và `recommend`
- [fuzzy.html](./fuzzy.html): màn hình kết quả fuzzy
- [planner.html](./planner.html): kế hoạch bữa ăn, gọi `plan`
- [map.html](./map.html): màn hình theo dõi giao hàng dùng custom geometry map từ dữ liệu tọa độ thật
- [map_quanquen.html](./map_quanquen.html): màn hình quán quen dùng custom geometry map từ dữ liệu recommend thật
- [detail.html](./detail.html): chi tiết món/quán, nhận món đã chọn từ frontend
- [tracking.html](./tracking.html): theo dõi đơn hàng
- [settings.html](./settings.html): cài đặt
- [navigation.js](./navigation.js): helper điều hướng dùng chung
- [api.js](./api.js): helper gọi API và lưu sessionStorage

---

## 2. Yêu cầu môi trường

Cần có:

- `Python 3.10+`
- Internet để gọi OpenWeather API
- Trình duyệt hiện đại như Chrome / Edge

Khuyên dùng thêm:

- `virtualenv` hoặc `venv`
- PowerShell trên Windows

---

## 3. Cài đặt dự án

### 3.1. Clone repo

```bash
git clone https://github.com/NaughMilk/PDTC-AI-FOOD.git
cd PDTC-AI-FOOD
```

### 3.2. Tạo môi trường ảo

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3.3. Cài thư viện

```bash
pip install -r requirements.txt
```

Nội dung hiện tại của `requirements.txt`:

- Flask
- numpy
- scikit-fuzzy
- requests
- python-dotenv
- folium

### 3.4. Tạo file `.env`

Tạo file `.env` cùng cấp với `smart_food_logic.py`.

Ví dụ:

```env
OPENWEATHER_API_KEY=your_openweather_api_key_here
```

Nếu không có API key, backend vẫn chạy nhưng phần weather sẽ fallback.

---

## 4. Cách khởi chạy dự án

### Cách A. Chạy đầy đủ qua Flask

Đây là cách khuyến nghị vì frontend và backend cùng origin, dễ test nhất.

```bash
python smart_food_logic.py
```

Sau khi chạy:

- backend mở ở `http://127.0.0.1:5000`
- route `/` sẽ trả về [login.html](./login.html)

Mở trình duyệt:

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

### Cách B. Chạy frontend riêng, backend riêng

Phù hợp khi bạn muốn test HTML trực tiếp.

Terminal 1:

```bash
python smart_food_logic.py
```

Terminal 2:

```bash
python -m http.server 4173
```

Sau đó mở:

- frontend static: [http://127.0.0.1:4173/login.html](http://127.0.0.1:4173/login.html)
- backend API: [http://127.0.0.1:5000](http://127.0.0.1:5000)

Trong mode này:

- HTML ở `:4173`
- API ở `:5000`
- frontend dùng [api.js](./api.js) để gọi chéo sang backend

---

## 5. Luồng dữ liệu hiện tại

### 5.1. Trang chủ

File: [home.html](./home.html)

Khi mở trang:

- gọi `GET /api/weather`
- lấy weather thật và render card thời tiết
- nếu đã có dữ liệu recommend trong `sessionStorage` thì dùng lại
- nếu chưa có thì gọi `POST /api/recommend` với payload mặc định

Khi bấm `Tìm món ăn phù hợp`:

- đọc slider `độ đói`, `ngân sách`, `thời gian`
- đọc `mục tiêu sức khỏe`
- gọi `POST /api/recommend`
- lưu kết quả vào `sessionStorage`
- chuyển sang [fuzzy.html](./fuzzy.html)

### 5.2. Fuzzy

File: [fuzzy.html](./fuzzy.html)

Trang này:

- đọc kết quả fuzzy từ `sessionStorage`
- nếu không có thì gọi lại `POST /api/recommend`
- render:
  - độ tương thích
  - món tốt nhất
  - các món gợi ý khác

### 5.3. Planner

File: [planner.html](./planner.html)

Trang này:

- gọi `POST /api/plan`
- lấy kế hoạch bữa sáng / trưa / tối thật từ backend
- phần `Phân tích tuần` hiện là `mock KPI chart`, không lấy từ backend

### 5.4. Map quán quen

File: [map_quanquen.html](./map_quanquen.html)

Trang này:

- lấy dữ liệu từ recommend gần nhất
- dùng `lat/lon` backend trả ra để vẽ custom map bằng `SVG + geometry`
- không dùng ảnh chụp map
- không dùng street tile map
- render danh sách card quán dưới cùng

### 5.5. Detail

File: [detail.html](./detail.html)

Trang này:

- nhận món đã chọn từ `sessionStorage`
- cập nhật tên món / tên quán / giá / ETA / khoảng cách

---

## 6. Cách test giao diện

### 6.1. Test flow cơ bản

1. Mở [http://127.0.0.1:5000](http://127.0.0.1:5000)
2. Xác nhận app vào `login.html`
3. Bấm `Đăng nhập`
4. Vào `Trang chủ`
5. Kiểm tra card thời tiết đã hiện dữ liệu thật
6. Thay đổi slider ở `Tìm kiếm thông minh`
7. Bấm `Tìm món ăn phù hợp`
8. Xác nhận `fuzzy.html` hiện món từ backend
9. Bấm `Đặt món ngay`
10. Xác nhận `detail.html` đổi theo món vừa chọn
11. Qua `Kế hoạch`
12. Xác nhận 3 bữa ăn được lấy từ backend
13. Qua `Bản đồ / Quán quen`
14. Xác nhận marker và card map lấy theo dữ liệu recommend

### 6.2. Checklist UI nên kiểm

`login.html`

- Card đăng nhập nằm giữa màn hình
- Không có layout phụ dư thừa
- Nút `Đăng nhập` chuyển được sang app

`home.html`

- Weather card lên đúng thời tiết
- Slider cập nhật label đúng
- Nút `Tìm món ăn phù hợp` hoạt động
- `Gợi ý món khác` và `Quán quen gần đây` có dữ liệu

`fuzzy.html`

- Match score hiển thị
- Món tốt nhất có giá, calo, ETA
- Card phụ render không lỗi màu/nền

`planner.html`

- 3 bữa ăn hiển thị đúng
- Chart KPI không tràn khung
- Legend đúng màu `Thực tế / Mục tiêu`

`map.html`

- `12 - 15 phút` không bị xuống dòng
- `19:45` không bị tách dòng
- phần đánh giá shipper có icon sao
- có thể kéo/pan bằng chuột hoặc touch
- là custom geometry map, không phải nền street tile

`map_quanquen.html`

- Marker hiển thị đủ
- Bottom carousel không bị nav che khi mở standalone
- có thể kéo/pan bằng chuột hoặc touch
- dữ liệu quán lấy từ backend

---

## 7. Cách test backend

### 7.1. Test nhanh bằng trình duyệt

Mở:

- [http://127.0.0.1:5000/api/weather](http://127.0.0.1:5000/api/weather)

Kỳ vọng:

- trả JSON thời tiết

### 7.2. Test bằng PowerShell

#### Weather

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/weather" -UseBasicParsing
```

#### Recommend

```powershell
$body = @{
  hunger = 7
  time_avail = 30
  budget = 300000
  health = "Balanced"
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "http://127.0.0.1:5000/api/recommend" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

#### Plan

```powershell
$body = @{
  profile = "Office Worker"
  late_night = $false
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "http://127.0.0.1:5000/api/plan" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

#### Map

Map cần dữ liệu `plan` hoặc `recommend` thật. Cách dễ nhất:

1. gọi `/api/plan`
2. copy trường `plan`
3. gửi lại cho `/api/map`

Ví dụ:

```powershell
$plan = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5000/api/plan" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"profile":"Office Worker","late_night":false}'

$mapBody = @{ items = $plan.plan } | ConvertTo-Json -Depth 6

Invoke-WebRequest `
  -Uri "http://127.0.0.1:5000/api/map" `
  -Method POST `
  -ContentType "application/json" `
  -Body $mapBody `
  -UseBasicParsing
```

### 7.3. Backend cần trả gì

`/api/weather`

- `weather`
- `weather_vi`
- `temp`
- `humidity`
- `wind`
- `traffic_value`

`/api/recommend`

- `urgency`
- `meal_score`
- `cal_target`
- `results[]`

Mỗi phần tử trong `results[]` nên có:

- `name`
- `rest_name`
- `price`
- `calo`
- `distance_km`
- `delivery_time`
- `lat`
- `lon`
- `match_pct`

`/api/plan`

- `plan[]`
- `total_calo`
- `weather`

`/api/map`

- `map_url`

---

## 8. Cách debug khi có lỗi

### Backend không lên

Kiểm tra:

- đã activate venv chưa
- đã `pip install -r requirements.txt` chưa
- thiếu `.env` thì weather fallback, nhưng backend vẫn phải chạy

### Frontend gọi API không được

Kiểm tra:

- Flask có đang chạy ở `:5000` không
- mở `http://127.0.0.1:5000/api/weather` có trả JSON không
- file [api.js](./api.js) đang dùng base URL:
  - cùng origin nếu chạy ở `:5000`
  - `http://127.0.0.1:5000` nếu chạy ở `:4173`

### Map / planner / fuzzy không có dữ liệu

Kiểm tra thứ tự:

1. `weather` có lên không
2. `/api/recommend` có trả `results` không
3. `/api/plan` có trả `plan` không
4. mở console browser xem lỗi fetch

### Geometry map không tương tác

Kiểm tra:

- đã reload cứng `Ctrl+F5` chưa
- JS mới của `map.html` / `map_quanquen.html` đã được tải chưa
- thao tác kéo bắt đầu từ vùng bản đồ, không phải từ card dưới cùng hay nút nổi

### Weather không đúng

Kiểm tra:

- API key OpenWeather
- mạng Internet
- quota hoặc lỗi từ OpenWeather

---

## 9. Ghi chú quan trọng

- Chart tuần trong [planner.html](./planner.html) hiện là `mock KPI`, không phản ánh dữ liệu backend
- `map.html` và `map_quanquen.html` hiện là `custom geometry map` từ dữ liệu tọa độ thật, không phải street map tile
- route trong `map.html` là tuyến mô phỏng hình học từ dữ liệu thật, chưa gọi dịch vụ routing ngoài
- Frontend hiện dùng `Tailwind CDN`, phù hợp cho demo/prototype; nếu production nên build CSS local

---

## 10. Lệnh nhanh cho người review

### Chạy dự án

```bash
python smart_food_logic.py
```

### Mở app

```text
http://127.0.0.1:5000
```

### Test frontend tách riêng

```bash
python -m http.server 4173
```

Mở:

```text
http://127.0.0.1:4173/login.html
```

### Test API nhanh

```text
GET  http://127.0.0.1:5000/api/weather
POST http://127.0.0.1:5000/api/recommend
POST http://127.0.0.1:5000/api/plan
POST http://127.0.0.1:5000/api/map
```

---

## 11. Tech stack

- Frontend: HTML, TailwindCSS, JavaScript
- Backend: Python, Flask
- Logic: scikit-fuzzy, numpy
- Weather: OpenWeatherMap
- Map: Folium

---

## 12. Trạng thái hiện tại

Đã nối:

- weather thật
- fuzzy recommend thật
- meal plan thật
- recent map geometry từ recommend thật
- tracking map geometry từ món đã chọn thật
- detail nhận món đã chọn

Chưa nối dữ liệu thật hoàn toàn:

- chart tuần planner
- order backend thực sự
- menu backend riêng cho `detail.html`
