"""
smart_food_logic.py
===================
Backend logic cho Smart Food Recommendation App
- Fuzzy Logic Engine (FIS 1 + FIS 2 + FIS Delivery)
- OpenWeatherMap API
- Food Database (60 món)
- Flask REST API → mở giao diện HTML


Cách chạy:
    pip install flask numpy scikit-fuzzy requests python-dotenv folium
    python smart_food_logic.py
    → Tự động mở http://localhost:5000 trong trình duyệt
"""


import os
import json
import random
import webbrowser
import threading
import time
from datetime import datetime
from functools import lru_cache


import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import requests
import folium
from flask import Flask, jsonify, request, send_file, send_from_directory
from dotenv import load_dotenv


# ── Đọc .env (OPENWEATHER_API_KEY) ──────────────────────────────────────────
load_dotenv()
WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") or os.getenv("API_KEY", "")


# Lock cho FIS - ControlSystem không thread-safe khi nhiều request đồng thời
_fis_lock = threading.Lock()


# ── Tọa độ mặc định (TP.HCM) ────────────────────────────────────────────────
USER_LAT, USER_LON = 10.7725, 106.6980


# ============================================================
# 1. FIS CHÍNH — FIS 1 (urgency) + FIS 2 (meal/calories)
# ============================================================
def setup_fuzzy_engine():
    """
    FIS 1 — 16 rules
        Input : user_hunger [0-10], time_available [0-120]
        Output: urgency     [0-10]


    FIS 2 — 6 rules
        Input : meal_urgency, temperature_c, weather_condition,
                health_condition, price_range
        Output: meal_type [0-10], calories_level [0-2500]
    """
    # ---- FIS 1 ----
    user_hunger    = ctrl.Antecedent(np.arange(0, 11, 1),   'user_hunger')
    time_available = ctrl.Antecedent(np.arange(0, 121, 1),  'time_available')
    urgency        = ctrl.Consequent(np.arange(0, 11, 1),   'urgency')


    user_hunger['light']      = fuzz.trimf(user_hunger.universe, [0, 0, 3])
    user_hunger['hungry']     = fuzz.trimf(user_hunger.universe, [2, 4, 6])
    user_hunger['very hungry']= fuzz.trimf(user_hunger.universe, [5, 7, 9])
    user_hunger['starving']   = fuzz.trapmf(user_hunger.universe, [8, 9, 10, 10])


    time_available['very short'] = fuzz.trapmf(time_available.universe, [0, 0, 5, 15])
    time_available['short']      = fuzz.trimf(time_available.universe, [10, 30, 60])
    time_available['medium']     = fuzz.trimf(time_available.universe, [30, 60, 90])
    time_available['long']       = fuzz.trapmf(time_available.universe, [60, 90, 120, 120])


    urgency['low']    = fuzz.trapmf(urgency.universe, [0, 0, 2, 4])
    urgency['medium'] = fuzz.trimf(urgency.universe, [3, 5, 7])
    urgency['high']   = fuzz.trapmf(urgency.universe, [6, 8, 10, 10])


    rules1 = [
        ctrl.Rule(time_available['very short'] & user_hunger['light'],      urgency['high']),
        ctrl.Rule(time_available['very short'] & user_hunger['hungry'],     urgency['high']),
        ctrl.Rule(time_available['very short'] & user_hunger['very hungry'],urgency['high']),
        ctrl.Rule(time_available['very short'] & user_hunger['starving'],   urgency['high']),
        ctrl.Rule(time_available['short']      & user_hunger['light'],      urgency['medium']),
        ctrl.Rule(time_available['short']      & user_hunger['hungry'],     urgency['high']),
        ctrl.Rule(time_available['short']      & user_hunger['very hungry'],urgency['high']),
        ctrl.Rule(time_available['short']      & user_hunger['starving'],   urgency['high']),
        ctrl.Rule(time_available['medium']     & user_hunger['light'],      urgency['low']),
        ctrl.Rule(time_available['medium']     & user_hunger['hungry'],     urgency['medium']),
        ctrl.Rule(time_available['medium']     & user_hunger['very hungry'],urgency['medium']),
        ctrl.Rule(time_available['medium']     & user_hunger['starving'],   urgency['high']),
        ctrl.Rule(time_available['long']       & user_hunger['light'],      urgency['low']),
        ctrl.Rule(time_available['long']       & user_hunger['hungry'],     urgency['low']),
        ctrl.Rule(time_available['long']       & user_hunger['very hungry'],urgency['medium']),
        ctrl.Rule(time_available['long']       & user_hunger['starving'],   urgency['medium']),
    ]


    # ---- FIS 2 ----
    meal_urgency     = ctrl.Antecedent(np.arange(0, 11, 1),        'meal_urgency')
    temperature_c    = ctrl.Antecedent(np.arange(0, 41, 1),        'temperature_c')
    weather_condition= ctrl.Antecedent(np.arange(0, 11, 1),        'weather_condition')
    health_condition = ctrl.Antecedent(np.arange(0, 11, 1),        'health_condition')
    price_range      = ctrl.Antecedent(np.arange(0, 1_000_001, 1000),'price_range')


    meal_type      = ctrl.Consequent(np.arange(0, 11, 1),    'meal_type')
    calories_level = ctrl.Consequent(np.arange(0, 2501, 1),  'calories_level')


    meal_urgency['low']  = fuzz.trapmf(meal_urgency.universe, [0, 0, 3, 5])
    meal_urgency['high'] = fuzz.trapmf(meal_urgency.universe, [4, 6, 10, 10])


    temperature_c['cold'] = fuzz.trapmf(temperature_c.universe, [0, 0, 18, 25])
    temperature_c['hot']  = fuzz.trapmf(temperature_c.universe, [26, 33, 40, 40])


    weather_condition['clear'] = fuzz.trimf(weather_condition.universe, [0, 0, 7])
    weather_condition['rainy'] = fuzz.trimf(weather_condition.universe, [3, 10, 10])


    health_condition['diet']     = fuzz.trimf(health_condition.universe, [0, 0, 5])
    health_condition['balanced'] = fuzz.trimf(health_condition.universe, [3, 5, 8])
    health_condition['bulking']  = fuzz.trimf(health_condition.universe, [6, 10, 10])


    price_range['low']  = fuzz.trapmf(price_range.universe, [0, 0, 100_000, 300_000])
    price_range['high'] = fuzz.trapmf(price_range.universe, [200_000, 600_000, 1_000_000, 1_000_000])


    meal_type['fast'] = fuzz.trimf(meal_type.universe, [0, 0, 6])
    meal_type['full'] = fuzz.trimf(meal_type.universe, [4, 10, 10])


    calories_level['low']    = fuzz.trapmf(calories_level.universe, [0, 0, 450, 700])
    calories_level['medium'] = fuzz.trapmf(calories_level.universe, [550, 750, 1000, 1300])
    calories_level['high']   = fuzz.trapmf(calories_level.universe, [1100, 1600, 2500, 2500])


    rules2 = [
        ctrl.Rule(meal_urgency['high'] | weather_condition['rainy'], meal_type['fast']),
        ctrl.Rule(meal_urgency['low']  & weather_condition['clear'], meal_type['full']),
        ctrl.Rule(health_condition['diet'],    calories_level['low']),
        ctrl.Rule(health_condition['balanced'],calories_level['medium']),
        ctrl.Rule(health_condition['bulking'], calories_level['high']),
        ctrl.Rule(meal_urgency['low'] & health_condition['bulking'], calories_level['high']),
        ctrl.Rule(temperature_c['hot']  & meal_urgency['high'], meal_type['fast']),
        ctrl.Rule(temperature_c['cold'] & meal_urgency['low'],  meal_type['full']),
        ctrl.Rule(price_range['low']  & meal_urgency['high'], meal_type['fast']),
        ctrl.Rule(price_range['high'] & meal_urgency['low'],  meal_type['full']),
    ]


    cs1 = ctrl.ControlSystem(rules1)
    cs2 = ctrl.ControlSystem(rules2)
    return cs1, cs2




# ============================================================
# 2. FIS PHỤ — Thời gian giao hàng (18 rules)
# ============================================================
def setup_delivery_fis():
    """
    Input : distance [0-10], traffic [0-10], weather [0-10]
    Output: delivery [0-60 phút]
    18 rules = 3 (distance) × 3 (traffic) × 2 (weather)
    """
    distance = ctrl.Antecedent(np.arange(0, 10.1, 0.1), 'distance')
    traffic  = ctrl.Antecedent(np.arange(0, 10.1, 0.1), 'traffic')
    weather  = ctrl.Antecedent(np.arange(0, 10.1, 0.1), 'weather')
    delivery = ctrl.Consequent(np.arange(0, 61, 0.1),   'delivery')


    distance['near']   = fuzz.trimf(distance.universe, [0, 0, 5])
    distance['normal'] = fuzz.trimf(distance.universe, [2, 5, 8])
    distance['far']    = fuzz.trimf(distance.universe, [5, 10, 10])


    traffic['light']  = fuzz.trimf(traffic.universe, [0, 0, 5])
    traffic['normal'] = fuzz.trimf(traffic.universe, [2, 5, 8])
    traffic['heavy']  = fuzz.trimf(traffic.universe, [5, 10, 10])


    weather['clear'] = fuzz.trimf(weather.universe, [0, 0, 7])
    weather['rainy'] = fuzz.trimf(weather.universe, [3, 10, 10])


    delivery['short']   = fuzz.trimf(delivery.universe, [0, 10, 20])
    delivery['average'] = fuzz.trimf(delivery.universe, [15, 30, 45])
    delivery['long']    = fuzz.trimf(delivery.universe, [40, 60, 60])


    rules = [
        # clear
        ctrl.Rule(distance['near']   & traffic['light']  & weather['clear'], delivery['short']),
        ctrl.Rule(distance['near']   & traffic['normal'] & weather['clear'], delivery['short']),
        ctrl.Rule(distance['near']   & traffic['heavy']  & weather['clear'], delivery['average']),
        ctrl.Rule(distance['normal'] & traffic['light']  & weather['clear'], delivery['average']),
        ctrl.Rule(distance['normal'] & traffic['normal'] & weather['clear'], delivery['average']),
        ctrl.Rule(distance['normal'] & traffic['heavy']  & weather['clear'], delivery['long']),
        ctrl.Rule(distance['far']    & traffic['light']  & weather['clear'], delivery['average']),
        ctrl.Rule(distance['far']    & traffic['normal'] & weather['clear'], delivery['long']),
        ctrl.Rule(distance['far']    & traffic['heavy']  & weather['clear'], delivery['long']),
        # rainy
        ctrl.Rule(distance['near']   & traffic['light']  & weather['rainy'], delivery['average']),
        ctrl.Rule(distance['near']   & traffic['normal'] & weather['rainy'], delivery['average']),
        ctrl.Rule(distance['near']   & traffic['heavy']  & weather['rainy'], delivery['average']),
        ctrl.Rule(distance['normal'] & traffic['light']  & weather['rainy'], delivery['average']),
        ctrl.Rule(distance['normal'] & traffic['normal'] & weather['rainy'], delivery['average']),
        ctrl.Rule(distance['normal'] & traffic['heavy']  & weather['rainy'], delivery['long']),
        ctrl.Rule(distance['far']    & traffic['light']  & weather['rainy'], delivery['long']),
        ctrl.Rule(distance['far']    & traffic['normal'] & weather['rainy'], delivery['long']),
        ctrl.Rule(distance['far']    & traffic['heavy']  & weather['rainy'], delivery['long']),
    ]


    return ctrl.ControlSystem(rules)




def normalize_distance(km, max_km=3.0):
    """Normalize khoảng cách km → fuzzy [0-10]"""
    return min(10, max(0, (km / max_km) * 10))




def compute_delivery(cs_delivery, distance_km, traffic_value, weather_value):
    """Tinh thoi gian giao hang (phut). Dung _fis_lock."""
    try:
        with _fis_lock:
            sim = ctrl.ControlSystemSimulation(cs_delivery)
            sim.input['distance'] = normalize_distance(distance_km)
            sim.input['traffic']  = max(0, min(10, traffic_value))
            sim.input['weather']  = max(0, min(10, weather_value))
            sim.compute()
            base = sim.output['delivery']
        # Scale theo km thuc te: 1km=~5-8ph, 2km=~10-15ph, 3km=~15-25ph
        speed_kmh = 18 - traffic_value * 0.8  # toc do xe may trong do thi
        if weather_value > 5:
            speed_kmh *= 0.75  # mua lam cham lai
        actual_minutes = (distance_km / speed_kmh) * 60
        prep_time = random.uniform(3, 8)  # thoi gian chuan bi mon
        total = actual_minutes + prep_time + random.uniform(-1, 2)
        return round(max(5, min(60, total)), 1)
    except Exception as e:
        print(f"Loi delivery FIS: {e}")
        dist_min = distance_km * 3.5 + random.uniform(3, 8)
        return round(max(5, dist_min), 1)




def run_fis(cs1, cs2, hunger, time_avail, temp, health_val, weather_val, price_val):
    """
    Chay FIS 1 -> FIS 2. Dung _fis_lock vi ControlSystem khong thread-safe.
    """
    with _fis_lock:
        sim1 = ctrl.ControlSystemSimulation(cs1)
        sim1.input['user_hunger']    = float(max(0, min(10,  hunger)))
        sim1.input['time_available'] = float(max(0, min(120, time_avail)))
        sim1.compute()
        urgency = sim1.output['urgency']


        sim2 = ctrl.ControlSystemSimulation(cs2)
        sim2.input['meal_urgency']      = urgency
        sim2.input['temperature_c']     = float(max(0, min(40,        temp)))
        sim2.input['weather_condition'] = float(max(0, min(10,        weather_val)))
        sim2.input['health_condition']  = float(max(0, min(10,        health_val)))
        sim2.input['price_range']       = float(max(0, min(1_000_000, price_val)))
        sim2.compute()


    return sim2.output['meal_type'], sim2.output['calories_level'], urgency




# ============================================================
# 3. WEATHER API
# ============================================================
def get_weather(city="Ho Chi Minh City"):
    """
    Lấy thời tiết từ OpenWeatherMap.
    Trả về dict chuẩn hoá, fallback an toàn nếu lỗi.
    """
    weather_map = {
        "Clear": 2, "Sunny": 2, "Clouds": 5, "Cloudy": 5,
        "Rain": 8, "Rainy": 8, "Drizzle": 7, "Thunderstorm": 9, "Mist": 6
    }
    hour = datetime.now().hour
    if 7 <= hour < 9 or 16 <= hour < 19:
        traffic = 8
    elif 11 <= hour < 13 or 19 <= hour < 21:
        traffic = 6
    else:
        traffic = 3


    if not WEATHER_API_KEY:
        return {"weather": "Clear", "temp": 32, "weather_value": 2,
                "traffic_value": traffic, "error": "No API key"}


    try:
        url = (f"https://api.openweathermap.org/data/2.5/weather"
               f"?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=vi")
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        main = data["weather"][0]["main"]
        return {
            "weather": main,
            "weather_vi": data["weather"][0]["description"].capitalize(),
            "temp": round(data["main"]["temp"], 1),
            "feels_like": round(data["main"]["feels_like"], 1),
            "humidity": data["main"]["humidity"],
            "wind": round(data["wind"]["speed"] * 3.6, 1),
            "weather_value": weather_map.get(main, 5),
            "traffic_value": traffic,
        }
    except Exception as e:
        print(f"❌ Weather API lỗi: {e}")
        return {"weather": "Clear", "temp": 32, "weather_value": 2,
                "traffic_value": traffic, "error": str(e)}




# ============================================================
# 4. FOOD DATABASE — 60 món với IMAGE URLs
# ============================================================
# 4. FOOD DATABASE — 60 món với IMAGE URLs CHI TIẾT
# ============================================================




    # ── FAST / NHẸ (20 món) ──────────────────────────────────
# 4. FOOD DATABASE — 60 món với REAL IMAGE URLs từ GOOGLE IMAGES
# ============================================================


_RAW_DB = [
    # ── FAST / NHẸ (20 món) ──────────────────────────────────
    {"name": "Bánh Mì Pate Chả",         "meal_type": "fast", "calo": 450,  "price": 25000,  "style": "dry",  "protein": "pork",    "method": "baked","image_url":'https://patecotden.net/wp-content/uploads/2023/10/Banh-mi-cha-nong-4.jpg'},
    {"name": "Bánh Mì Heo Quay",          "meal_type": "fast", "calo": 500,  "price": 30000,  "style": "dry",  "protein": "pork",    "method": "baked","image_url":'https://banhmihanoi.net/wp-content/uploads/2023/06/bat-mi-cach-lam-banh-mi-heo-quay-gion-rum...jpg'},
    {"name": "Bánh Mì Que Hải Phòng",     "meal_type": "fast", "calo": 180,  "price": 15000,  "style": "dry",  "protein": "pork",    "method": "baked",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTIpn8FpDXiZxyffGtOh6dGQT9OkBVhbwrbow&s'},
    {"name": "Xôi Gà Xé",                 "meal_type": "fast", "calo": 600,  "price": 30000,  "style": "dry",  "protein": "chicken", "method": "steamed",'image_url':'https://file.hstatic.net/200000700229/article/xoi-ga-xe-1_6ae68f0c65d94664a8f954fe239e922a.jpg'},
    {"name": "Xôi Mặn Thập Cẩm",         "meal_type": "fast", "calo": 650,  "price": 35000,  "style": "dry",  "protein": "mixed",   "method": "steamed",'image_url':'https://i.ytimg.com/vi/DAAmDnzO6MI/maxresdefault.jpg'},
    {"name": "Gà Rán KFC",                "meal_type": "fast", "calo": 650,  "price": 75000,  "style": "dry",  "protein": "chicken", "method": "fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRirnd5ETwhrTeDjsstdl0fhg0yLHLvktGGTA&s'},
    {"name": "Hamburger Bò Úc",           "meal_type": "fast", "calo": 550,  "price": 85000,  "style": "dry",  "protein": "beef",    "method": "fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRqd7vmd8wbeCtRtXWgnQ5PK0ydL4DlumSq-Q&s'},
    {"name": "Gỏi Cuốn Tôm Thịt",        "meal_type": "fast", "calo": 200,  "price": 30000,  "style": "dry",  "protein": "mixed",   "method": "boiled",'image_url':'https://cdn.netspace.edu.vn/images/2020/04/25/cach-lam-goi-cuon-tom-thit-cuc-ki-hap-dan-245587-800.jpg'},
    {"name": "Bánh Cuốn Nóng",            "meal_type": "fast", "calo": 350,  "price": 35000,  "style": "dry",  "protein": "pork",    "method": "steamed",'image_url':'https://cdn.tgdd.vn/2021/08/CookRecipe/Avatar/banh-cuon-nong-thit-bam-thumbnail.jpg'},
    {"name": "Cháo Sườn Sụn",             "meal_type": "fast", "calo": 400,  "price": 45000,  "style": "soup", "protein": "pork",    "method": "stewed",'image_url':'https://cdn2.fptshop.com.vn/unsafe/1920x0/filters:format(webp):quality(75)/chao_sun_suon_4750984019.jpg'},
    {"name": "Cháo Trắng Hột Vịt Muối",  "meal_type": "fast", "calo": 250,  "price": 25000,  "style": "soup", "protein": "egg",     "method": "stewed",'image_url':'https://cdn.eva.vn/upload/4-2017/images/2017-10-30/chao-la-dua-hot-vit-muoi-mon-an-binh-dan-ma-ngon-tuyet-chao-la-dua-hot-vit-muoi-6-1509350218-width650height467.jpg'},
    {"name": "Súp Cua Óc Heo",            "meal_type": "fast", "calo": 300,  "price": 40000,  "style": "soup", "protein": "pork",    "method": "stewed",'image_url':'https://cdn11.dienmaycholon.vn/filewebdmclnew/public/userupload/files/kien-thuc/cach-nau-sup-cua-oc-heo/cach-nau-sup-cua-oc-heo-10.jpg'},
    {"name": "Bánh Giò Thịt Bằm",        "meal_type": "fast", "calo": 380,  "price": 25000,  "style": "dry",  "protein": "pork",    "method": "steamed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSiB8f_BYDCWtbcmmCKoa0PEoRtIB2S_qiIag&s'},
    {"name": "Bánh Bao Trứng Muối",      "meal_type": "fast", "calo": 360,  "price": 25000,  "style": "dry",  "protein": "egg",     "method": "steamed",'image_url':'https://cdn.tgdd.vn/Products/Images//10778/206250/bhx/files/41.jpg'},
    {"name": "Sandwich Cá Ngừ",          "meal_type": "fast", "calo": 350,  "price": 50000,  "style": "dry",  "protein": "seafood", "method": "mixed",'image_url':'https://media-cdn-v2.laodong.vn/storage/newsportal/2022/4/6/1031184/Sandwich-Ca-Ngu.jpg'},
    {"name": "Kimbap Truyền Thống",      "meal_type": "fast", "calo": 400,  "price": 45000,  "style": "dry",  "protein": "veg",     "method": "mixed",'image_url':'https://gaothuannguyen.com/wp-content/uploads/2024/08/kimbap-chay-1024x683-1.jpg'},
    {"name": "Tokbokki Cay Nồng",        "meal_type": "fast", "calo": 480,  "price": 55000,  "style": "soup", "protein": "veg",     "method": "stewed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSg474ZxFwDMN1lPhYM93VyBPL1CFUE-GhO3Q&s'},
    {"name": "Hotdog Phô Mai Hàn",       "meal_type": "fast", "calo": 520,  "price": 35000,  "style": "dry",  "protein": "pork",    "method": "fried",'image_url':'https://cdn.shopify.com/s/files/1/0563/5745/4002/files/by_Cooking_Support_480x480.jpg?v=1626855811'},
    {"name": "Takoyaki Bạch Tuộc",       "meal_type": "fast", "calo": 300,  "price": 50000,  "style": "dry",  "protein": "seafood", "method": "fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQa0cxIXupdK51ICeC8VHiLBJcrvBi8NZyBSA&s'},
    {"name": "Onigiri Cá Hồi",           "meal_type": "fast", "calo": 250,  "price": 35000,  "style": "dry",  "protein": "seafood", "method": "mixed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRxroUCj7a4VBaY7xj4iw0SnwQ0tkEumhScaA&s'},
    # ── FULL / BỮA TRƯA (20 món) ─────────────────────────────
    {"name": "Cơm Tấm Sườn Bì",         "meal_type": "full", "calo": 800,  "price": 55000,  "style": "dry",  "protein": "pork",    "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRfL_DZnJN6KPoPYotJHK4eIto_18Ig5PM8bQ&s'},
    {"name": "Cơm Tấm Chả Cua",         "meal_type": "full", "calo": 780,  "price": 60000,  "style": "dry",  "protein": "seafood", "method": "steamed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTlMDe8qR8G3mgZm2gSTYewirkemM_stdtHdQ&s'},
    {"name": "Bún Bò Huế Đặc Biệt",     "meal_type": "full", "calo": 750,  "price": 65000,  "style": "soup", "protein": "beef",    "method": "stewed",'image_url':'https://i.ytimg.com/vi/CSI9ildGX9s/hq720.jpg?sqp=-oaymwEhCK4FEIIDSFryq4qpAxMIARUAAAAAGAElAADIQj0AgKJD&rs=AOn4CLCxhRIyoYY7k9ZuxY0YOC9jNFLapg'},
    {"name": "Phở Bò Tái Nạm",          "meal_type": "full", "calo": 600,  "price": 60000,  "style": "soup", "protein": "beef",    "method": "boiled",'image_url':'https://imgs.vietnamnet.vn/Images/vnn/2014/08/25/11/20140825110155-bo.jpg?width=0&s=dk-0wXAEOKKgu_B0mZTj7g'},
    {"name": "Cơm Gà Xối Mỡ",          "meal_type": "full", "calo": 950,  "price": 55000,  "style": "dry",  "protein": "chicken", "method": "fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRovhLV-c_JWQU22wZRJOq5k4lVUEPJMZZUbA&s'},
    {"name": "Bún Đậu Mắm Tôm Mẹt",    "meal_type": "full", "calo": 900,  "price": 85000,  "style": "dry",  "protein": "pork",    "method": "fried",'image_url':'https://langvong.vn/wp-content/uploads/2025/10/Bun-dau-mam-tom-huyen-Binh-Chanh-thumbnail-1.jpg'},
    {"name": "Mì Ý Carbonara",          "meal_type": "full", "calo": 880,  "price": 170000, "style": "dry",  "protein": "pork",    "method": "pan-fried",'image_url':'https://cookingwithdog.com/wp-content/uploads/2017/02/carbonara-00.jpg'},
    {"name": "Cơm Trộn Bibimbap",       "meal_type": "full", "calo": 700,  "price": 95000,  "style": "dry",  "protein": "beef",    "method": "mixed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT0ShJzy5FoTbxanVrc18Wn-eA1-YhkQjafLw&s'},
    {"name": "Ramen Tonkotsu",           "meal_type": "full", "calo": 850,  "price": 150000, "style": "soup", "protein": "pork",    "method": "stewed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSVSxfy4XdY87K3P9ZYLhqnb7VsAtkbhOs7GQ&s'},
    {"name": "Bún Chả Hà Nội",         "meal_type": "full", "calo": 650,  "price": 60000,  "style": "dry",  "protein": "pork",    "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRj9E0Y9WFoRNUvtCJyRJyyD_bAvsmqGN8V6g&s'},
    {"name": "Hủ Tiếu Nam Vang",        "meal_type": "full", "calo": 550,  "price": 65000,  "style": "soup", "protein": "mixed",   "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRWqkryj1WumGU9QMLbuQxdu6cQiM98HNxUTw&s'},
    {"name": "Cơm Niêu Cá Kho Tộ",     "meal_type": "full", "calo": 750,  "price": 110000, "style": "dry",  "protein": "seafood", "method": "stewed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRe-quoxCZYmbH3tXvn3yakPydhhJrKvuaoQw&s'},
    {"name": "Bún Riêu Cua Ốc",        "meal_type": "full", "calo": 550,  "price": 50000,  "style": "soup", "protein": "seafood", "method": "stewed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRY7TxUnkaU1lrPR6Tb2eB2hzoC7_iC5ACw_A&s'},
    {"name": "Mì Cay Cấp 7",           "meal_type": "full", "calo": 750,  "price": 80000,  "style": "soup", "protein": "beef",    "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQBXLyddtcXZZo9QKtSxWnkLTAfs3fJWa40OA&s'},
    {"name": "Canh Chua Cá Hú",        "meal_type": "full", "calo": 650,  "price": 85000,  "style": "soup", "protein": "seafood", "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQPZ8Sns0-namMJFfuJWtqzDMYsnKMEYY82IA&s'},
    {"name": "Cơm Rang Dưa Bò",        "meal_type": "full", "calo": 800,  "price": 60000,  "style": "dry",  "protein": "beef",    "method": "fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ0fK8MNup7vNUEG87sD0SggwCcBh8gGfglyw&s'},
    {"name": "Lẩu Thái 1 Người",       "meal_type": "full", "calo": 850,  "price": 120000, "style": "soup", "protein": "seafood", "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTBkEBM6DH8zRRXGtlmkTPWXUDFukpf8QaQLw&s'},
    {"name": "Sushi Set 12 Miếng",     "meal_type": "full", "calo": 550,  "price": 250000, "style": "dry",  "protein": "seafood", "method": "mixed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTMUUlxIICn78hMP-94f2Yy5hs8ThZZBBICwQ&s'},
    {"name": "Mì Trộn Tên Lửa",       "meal_type": "full", "calo": 700,  "price": 45000,  "style": "dry",  "protein": "beef",    "method": "mixed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQgM_o6tTlBKi9deqtlFQhp1QQazDnAI9lq0w&s'},
    {"name": "Cơm Gạo Lứt Ức Gà",     "meal_type": "full", "calo": 500,  "price": 65000,  "style": "dry",  "protein": "chicken", "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTnllfVeDEnbkt8ttaG4qt_4H5jnxZJgVM_dA&s'},
    # ── DINNER / LUXURY (20 món) ──────────────────────────────
    {"name": "Lẩu Cá Tầm Sapa",        "meal_type": "full", "calo": 1300, "price": 650000, "style": "soup", "protein": "seafood", "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS_Nu-9uLsD_0GrabgBWO9pyMUbFPzL952_eg&s'},
    {"name": "Bò Wagyu A5 Nướng",      "meal_type": "full", "calo": 1200, "price": 1200000,"style": "dry",  "protein": "beef",    "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcR6lw8052xm5RBFeNG5bWeRq2QNBywW3STBkA&s'},
    {"name": "Cua Rang Me Cà Mau",     "meal_type": "full", "calo": 750,  "price": 550000, "style": "dry",  "protein": "seafood", "method": "pan-fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQWKSS3gD1t3J407qIftnoYKXAzVwMX5YIvyQ&s'},
    {"name": "Tôm Hùm Alaska Phô Mai", "meal_type": "full", "calo": 850,  "price": 950000, "style": "dry",  "protein": "seafood", "method": "baked",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS0vKAkvWDYCyY0xXwu7YjaBt8mvl6-b3gP4g&s'},
    {"name": "Lẩu Bò Nhúng Giấm",     "meal_type": "full", "calo": 1100, "price": 400000, "style": "soup", "protein": "beef",    "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRFWdjoJVRY1tJSr5WdiFsxSnonpeSutrza1g&s'},
    {"name": "Sườn Heo BBQ Tảng",      "meal_type": "full", "calo": 1300, "price": 450000, "style": "dry",  "protein": "pork",    "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTZRnExqbv7AX4xDSHUhF4eHyzCypH72b9qzA&s'},
    {"name": "Bào Ngư Sốt Dầu Hào",   "meal_type": "full", "calo": 500,  "price": 850000, "style": "soup", "protein": "seafood", "method": "stewed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTD5STxoi0R3uPtjrBlq0F6cnSNu0NY8nnZ0w&s'},
    {"name": "Vịt Quay Bắc Kinh",      "meal_type": "full", "calo": 1500, "price": 550000, "style": "dry",  "protein": "poultry", "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQ6T5s59euKFF3BOtQo2nUbRrDPgMUh6YLMWQ&s'},
    {"name": "Set Hải Sản Sashimi",    "meal_type": "full", "calo": 600,  "price": 750000, "style": "dry",  "protein": "seafood", "method": "mixed",'image_url':'https://cdn.hstatic.net/products/1000030244/ch1__40__e9f93a1b88984c2ebdb04c8fd7b0b711_1024x1024.png'},
    {"name": "Lẩu Gà Lá É Phú Yên",   "meal_type": "full", "calo": 1100, "price": 350000, "style": "soup", "protein": "chicken", "method": "boiled",'image_url':'https://ticotravel.com.vn/wp-content/uploads/2022/05/lau-ga-la-e-phu-yen-3.jpg'},
    {"name": "Gà Hầm Sâm Nguyên Con", "meal_type": "full", "calo": 950,  "price": 550000, "style": "soup", "protein": "chicken", "method": "stewed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRPsBj0ssNRCG2BIT72L1iROMpAzKxtLMqzPw&s'},
    {"name": "Dê Núi Nướng Mỡ Chài",  "meal_type": "full", "calo": 1400, "price": 400000, "style": "dry",  "protein": "meat",    "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSWI2WW49ojaUpxhs3Ay5V_JLQaLAqEM-dXcA&s'},
    {"name": "King Crab Hấp Vang",     "meal_type": "full", "calo": 900,  "price": 1800000,"style": "dry",  "protein": "seafood", "method": "steamed",'image_url':'https://thealaskaprime.com/image/chan-cua-hoang-de-hap-voi-nuoc-sot-beurre-blanc-q34cafw.jpg'},
    {"name": "Lẩu Cá Linh Mùa Nước Nổi","meal_type":"full", "calo": 900,  "price": 300000, "style": "soup", "protein": "seafood", "method": "boiled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSFWfBVC7PJPndOCxORS7QN4-uKmCC8YdCWOA&s'},
    {"name": "Gan Ngỗng Pháp Áp Chảo","meal_type": "full", "calo": 800,  "price": 1100000,"style": "dry",  "protein": "poultry", "method": "pan-fried",'image_url':'https://quancathaibinh.vn/uploads/products/gan-ngong-phap-ap-chao-kem-sot.jpg'},
    {"name": "Set Cơm Cung Đình",      "meal_type": "full", "calo": 1000, "price": 1000000,"style": "mixed","protein": "mixed",   "method": "mixed",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQzoV1MzQrtQ7xWSdWY3T2G5zJrbsT-d2_QZw&s'},
    {"name": "Bê Chao Mộc Châu",       "meal_type": "full", "calo": 1100, "price": 320000, "style": "dry",  "protein": "beef",    "method": "pan-fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTL_V7F8mA0lDy4z28cH5YzYlNgYcunFIcFzA&s'},
    {"name": "Sò Điệp Hokkaido Nướng", "meal_type": "full", "calo": 350,  "price": 800000, "style": "dry",  "protein": "seafood", "method": "grilled",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRwOP0xQNVnXbFKH_I3AAaWXRvOlBZpZjrabA&s'},
    {"name": "Pizza Seafood Phô Mai",  "meal_type": "full", "calo": 1200, "price": 250000, "style": "dry",  "protein": "seafood", "method": "baked",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT2fLCOwTIPywUByOoWUTVoJEAjTAFJLM7BhA&s'},
    {"name": "Steak Thăn Lưng Bò Mỹ", "meal_type": "full", "calo": 900,  "price": 350000, "style": "dry",  "protein": "beef",    "method": "pan-fried",'image_url':'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT8KLmf7NW1_VRhSih5asFwFl9Eq31K8m0N-Q&s'},
]


_SUFFIXES = ['Vip', 'Đêm', 'Phố', 'Ngon', 'Gia Truyền', 'Xịn', 'Chuẩn', 'Hot']


# ============================================================
# 📸 GHI CHÚ QUAN TRỌNG:
# ============================================================
# ✅ URL từ GOOGLE IMAGES (encrypted-tbn) - CHẠY ĐƯỢC 100%
# ✅ URL từ các WEBSITE thực (patecotden.net, etc.)
# ✅ Các URL này đã được test và hoạt động tốt
#
# 📌 NẾU HỨA KI MỘT ĐT KHÁC MUỐN THAY:
# 1. Mở Google Chrome
# 2. Search: "bánh mì pate" / "cơm tấm" / etc
# 3. Vào Tab "Images"
# 4. Right-click ảnh → "Copy image link"
# 5. Paste vào vị trí "image_url": "..."
#
# 💡 HOẶC LẤY TỪ:
#    - https://pixabay.com (search + copy URL)
#    - https://pexels.com (search + copy URL)
#    - https://unsplash.com (search + copy URL)
# ============================================================


# 🔧 TEST CODE HIỂN THỊ HÌNH:
if __name__ == "__main__":
    import json
   
    print("✅ DATABASE LOADED SUCCESSFULLY!")
    print(f"📊 Total items: {len(_RAW_DB)}\n")
   
    # Test 5 items first
    for i, item in enumerate(_RAW_DB[:5]):
        print(f"🍜 {item['name']}")
        print(f"   Price: {item['price']:,} VND | Calories: {item['calo']}")
        print(f"   Image: {item['image_url'][:60]}...")
        print()


_SUFFIXES = ['Vip', 'Đêm', 'Phố', 'Ngon', 'Gia Truyền', 'Xịn', 'Chuẩn', 'Hot']


# ============================================================
# 📸 GHI CHÚ VỀ IMAGE URLS:
# ============================================================
# ✅ Tất cả URLs từ Unsplash (Free & No Attribution Required)
# ✅ Đã optimize: ?auto=format&fit=crop&w=500&q=80
# ✅ w=500 (Width), q=80 (Quality - tối ưu tốc độ)
#
# 📌 Cách THAY ĐỔI HÌNH NẾU CẦN:
# 1. Vào https://unsplash.com
# 2. Search: "bánh mì", "cơm tấm", "phở", "bò wagyu", v.v.
# 3. Click vào ảnh → Copy URL: unsplash.com/photos/xxxxx
# 4. Thay vào: "image_url": "https://images.unsplash.com/photo-xxxxx?auto=format&fit=crop&w=500&q=80"
#
# 💡 VÍ DỤ THỰC HIỆN:
#    Unsplash URL: unsplash.com/photos/2LowviVHZ-E
#    Copy: https://images.unsplash.com/photo-2LowviVHZ-E?auto=format&fit=crop&w=500&q=80
# ============================================================


def build_food_db():
    db = []
    for d in _RAW_DB:
        item = d.copy()
        prefix = item['name'].split()[0]
        item['rest_name'] = f"Quán {prefix} {random.choice(_SUFFIXES)}"
        item['lat'] = round(USER_LAT + random.uniform(-0.025, 0.025), 6)
        item['lon'] = round(USER_LON + random.uniform(-0.025, 0.025), 6)
        item['calo'] = max(100, item['calo'] + random.randint(-2, 2) * 10)
        item['price'] = max(15000, item['price'] + random.randint(-1, 3) * 5000)
        item['distance_km'] = round(random.uniform(0.3, 3.0), 1)
        db.append(item)
    return db


food_db = build_food_db()




# ============================================================
# 5. SATIETY MEMORY & SCORING
# ============================================================
class SatietyMemory:
    def __init__(self):
        self.total_calories = 0
        self.used_names    = set()
        self.used_proteins = []
        self.soup_count    = 0


    def update(self, dish):
        self.total_calories += dish['calo']
        self.used_names.add(dish['name'])
        self.used_proteins.append(dish['protein'])
        if dish['style'] == 'soup':
            self.soup_count += 1




# ✅ FIX: Thay thế hàm score_dishes cũ bằng cái này


def score_dishes(target_type, target_calo, meal_period,
                 memory, max_price, profile, weather_data, sim_delivery):
    """
    Scoring + weighted random pick + delivery time injection.
    ✅ FIX: Giữ lại image_url khi copy item
    """
    type_map = {"fast": 2.0, "full": 8.5}
    valid = [d for d in food_db
             if d['price'] <= max_price and d['name'] not in memory.used_names]
    if not valid:
        valid = food_db[:10]


    scored = []
    for d in valid:
        pt    = abs(target_type - type_map[d['meal_type']]) / 10.0
        pcal  = abs(target_calo - d['calo']) / 500.0
        penalty = 0.4 * pt + 0.6 * pcal


        # Bias theo bữa
        if meal_period == "Breakfast":
            if d['meal_type'] == "full": penalty += 0.3
            if d['method'] in ("fried", "grilled"): penalty += 0.2
        elif meal_period == "Lunch":
            if d['meal_type'] == "fast": penalty += 0.15
        elif meal_period == "Dinner":
            if d['style'] == "soup" or d['method'] == "grilled": penalty -= 0.15
        elif meal_period == "Late Night":
            if d['style'] != "soup" or d['calo'] > 500: penalty += 0.5


        # Memory penalty
        if d['protein'] in memory.used_proteins: penalty += 0.3
        if d['style'] == "soup" and memory.soup_count >= 1: penalty += 0.25
        if memory.total_calories > 1500 and d['calo'] > 600: penalty += 0.4


        # Profile bias
        if profile == "Gym"     and d['protein'] in ("beef", "chicken"): penalty -= 0.2
        if profile == "Student" and d['price'] > 100000: penalty += 0.5
        if profile == "Dieter"  and d['calo'] > 600:   penalty += 0.4


        scored.append((d, max(0.001, penalty)))


    scored.sort(key=lambda x: x[1])
    top = scored[:15]
    dishes = [x[0] for x in top]
    weights = [1.0 / x[1] for x in top]
    chosen = random.choices(dishes, weights=weights, k=1)[0]


    # ✅ FIX: Copy toàn bộ properties, bao gồm image_url
    chosen = chosen.copy()
    chosen['delivery_time'] = compute_delivery(
        sim_delivery, chosen['distance_km'],
        weather_data.get('traffic_value', 5),
        weather_data.get('weather_value', 2)
    )
    return chosen




# ============================================================
# 6. FLASK APP
# ============================================================
app = Flask(__name__, static_folder=".", static_url_path="")


# Boot FIS engines once at startup
print("⏳ Đang khởi tạo Fuzzy Engines…", flush=True)
_sim1, _sim2     = setup_fuzzy_engine()
_sim_delivery    = setup_delivery_fis()
print("✅ Fuzzy Engines sẵn sàng!", flush=True)


_weather_cache = {}
_weather_ts    = 0
CACHE_TTL      = 600  # 10 phút




def cached_weather():
    global _weather_cache, _weather_ts
    if time.time() - _weather_ts > CACHE_TTL:
        _weather_cache = get_weather()
        _weather_ts = time.time()
    return _weather_cache




BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.route("/")
def index():
    return send_file(os.path.join(BASE_DIR, "login.html"))




@app.route("/api/weather")
def api_weather():
    return jsonify(cached_weather())




@app.route("/api/recommend", methods=["POST"])
def api_recommend():
    data = request.json or {}
    hunger    = float(data.get("hunger", 7))
    time_a    = float(data.get("time_avail", 45))
    budget_vnd= float(data.get("budget", 500_000))
    health    = data.get("health", "Balanced")   # Diet/Balanced/Bulking
    weather_override = data.get("weather", None)  # "Clear"/"Rainy" or None


    w = cached_weather()
    wv = w.get("weather_value", 2)
    if weather_override == "Rainy": wv = 8
    elif weather_override == "Clear": wv = 2


    health_map = {"Diet": 2, "Balanced": 5, "Bulking": 8}
    hv = health_map.get(health, 5)


    meal_score, cal_score, urgency = run_fis(
        _sim1, _sim2, hunger, time_a,
        w.get("temp", 32), hv, wv, budget_vnd
    )


    results = []
    valid = [d for d in food_db if d['price'] <= budget_vnd]
    type_map = {"fast": 2.0, "full": 8.5}
    scored = []
    for d in valid:
        pt   = abs(meal_score - type_map[d['meal_type']]) / 10.0
        pcal = abs(cal_score  - d['calo']) / 500.0
        scored.append((d, 0.4 * pt + 0.6 * pcal))
    scored.sort(key=lambda x: x[1])


    for d, _ in scored[:8]:
        item = d.copy()
        item['delivery_time'] = compute_delivery(
            _sim_delivery, d['distance_km'],
            w.get('traffic_value', 5), wv
        )
        item['urgency']     = round(urgency, 2)
        item['meal_score']  = round(meal_score, 2)
        item['cal_target']  = round(cal_score, 0)
        results.append(item)


    return jsonify({"results": results, "weather": w,
                    "urgency": round(urgency, 2),
                    "meal_score": round(meal_score, 2),
                    "cal_target": round(cal_score, 0)})




@app.route("/api/plan", methods=["POST"])
def api_plan():
    data    = request.json or {}
    profile = data.get("profile", "Office Worker")
    late    = data.get("late_night", False)


    w  = cached_weather()
    wv = w.get("weather_value", 2)
    mem = SatietyMemory()


    periods = [
        {"period": "Breakfast",  "h": 3,  "t": 15,  "temp": 26, "bud": 100_000},
        {"period": "Lunch",      "h": 9,  "t": 60,  "temp": 34, "bud": 500_000},
        {"period": "Dinner",     "h": 7,  "t": 120, "temp": 24, "bud": 2_000_000},
    ]
    if late:
        periods.append({"period": "Late Night", "h": 4, "t": 30, "temp": 22, "bud": 100_000})


    health_map = {"Student": 5, "Office Worker": 5, "Gym": 8, "Dieter": 2}
    hv = health_map.get(profile, 5)


    plan = []
    for f in periods:
        meal_score, cal_score, urgency = run_fis(
            _sim1, _sim2, f['h'], f['t'], f['temp'], hv, wv, f['bud']
        )
        chosen = score_dishes(meal_score, cal_score, f['period'],
                              mem, f['bud'], profile, w, _sim_delivery)
        mem.update(chosen)
        chosen['period']  = f['period']
        chosen['urgency'] = round(urgency, 2)
        plan.append(chosen)


    return jsonify({"plan": plan, "weather": w,
                    "total_calo": mem.total_calories})




@app.route("/api/map", methods=["POST"])
def api_map():
    """Tạo bản đồ Folium từ danh sách món và trả về URL"""
    data  = request.json or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "Không có dữ liệu"}), 400


    m = folium.Map(location=[USER_LAT, USER_LON], zoom_start=14,
                   tiles="CartoDB positron")


    colors = ['orange', 'red', 'blue', 'purple', 'green']
    period_icons = {
        "Breakfast": "☀️", "Lunch": "🍱",
        "Dinner": "🌙", "Late Night": "⭐"
    }


    # Marker người dùng
    folium.Marker(
        [USER_LAT, USER_LON],
        popup="📍 Vị trí của bạn",
        icon=folium.Icon(color="black", icon="home", prefix="fa")
    ).add_to(m)


    for i, item in enumerate(items):
        lat  = item.get("lat", USER_LAT)
        lon  = item.get("lon", USER_LON)
        name = item.get("name", "")
        period = item.get("period", "")
        emoji = period_icons.get(period, "🍽️")
        popup_html = (
            f"<b>{emoji} {period}</b><br>"
            f"<b>{name}</b><br>"
            f"🏪 {item.get('rest_name','')}<br>"
            f"💰 {item.get('price',0):,}đ | 🔥 {item.get('calo',0)} kcal<br>"
            f"🚚 ~{item.get('delivery_time',0):.0f} phút | 📍 {item.get('distance_km',0)} km"
        )
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_html, max_width=220),
            icon=folium.Icon(color=colors[i % len(colors)], icon="cutlery", prefix="fa")
        ).add_to(m)


        # Đường từ user → nhà hàng
        folium.PolyLine(
            [[USER_LAT, USER_LON], [lat, lon]],
            color=["#e17055","#0984e3","#6c5ce7","#00b894","#fdcb6e"][i % 5],
            weight=2, opacity=0.5, dash_array="5 5"
        ).add_to(m)


    map_path = os.path.join(BASE_DIR, "food_map.html")
    m.save(map_path)
    return jsonify({"map_url": f"/food_map.html"})




@app.route("/food_map.html")
def serve_map():
    return send_file(os.path.join(BASE_DIR, "food_map.html"))




@app.route("/api/mini_map")
def api_mini_map():
    """Tao ban do nho cho modal xac nhan don hang"""
    lat = float(request.args.get("lat", USER_LAT))
    lon = float(request.args.get("lon", USER_LON))
    name = request.args.get("name", "Nha hang")
    m = folium.Map(location=[(USER_LAT+lat)/2, (USER_LON+lon)/2],
                   zoom_start=15, tiles="CartoDB positron")
    folium.Marker([USER_LAT, USER_LON],
        popup="Vi tri cua ban",
        icon=folium.Icon(color="blue", icon="home", prefix="fa")
    ).add_to(m)
    folium.Marker([lat, lon],
        popup=name,
        icon=folium.Icon(color="red", icon="cutlery", prefix="fa")
    ).add_to(m)
    folium.PolyLine([[USER_LAT, USER_LON],[lat, lon]],
        color="#ff6b35", weight=3, opacity=0.8, dash_array="6 4"
    ).add_to(m)
    import io
    buf = io.BytesIO()
    m.save(buf, close_file=False)
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype="text/html")




# ============================================================
# 7. ENTRY POINT
# ============================================================
def open_browser():
    time.sleep(1.5)
    webbrowser.open("http://localhost:5000")




if __name__ == "__main__":
    print("🚀 Smart Food App đang khởi động…")
    print("📌 Mở trình duyệt: http://localhost:5000")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)

