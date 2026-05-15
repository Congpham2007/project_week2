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
    """Tính thời gian giao hàng (phút) - tạo sim mới mỗi lần"""
    try:
        sim = ctrl.ControlSystemSimulation(cs_delivery)
        sim.input['distance'] = normalize_distance(distance_km)
        sim.input['traffic']  = max(0, min(10, traffic_value))
        sim.input['weather']  = max(0, min(10, weather_value))
        sim.compute()
        return round(sim.output['delivery'], 1)
    except Exception as e:
        print(f"⚠️  Lỗi delivery FIS: {e}")
        return 30.0


def run_fis(cs1, cs2, hunger, time_avail, temp, health_val, weather_val, price_val):
    """
    Chạy FIS 1 → FIS 2, tạo simulation mới mỗi lần để tránh shared state.
    """
    sim1 = ctrl.ControlSystemSimulation(cs1)
    sim1.input['user_hunger']    = float(hunger)
    sim1.input['time_available'] = float(time_avail)
    sim1.compute()
    urgency = sim1.output['urgency']

    sim2 = ctrl.ControlSystemSimulation(cs2)
    sim2.input['meal_urgency']      = urgency
    sim2.input['temperature_c']     = float(temp)
    sim2.input['weather_condition'] = float(weather_val)
    sim2.input['health_condition']  = float(health_val)
    sim2.input['price_range']       = float(price_val)
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
# 4. FOOD DATABASE — 60 món
# ============================================================
_RAW_DB = [
    # ── FAST / NHẸ (20 món) ──────────────────────────────────
    {"name": "Bánh Mì Pate Chả",         "meal_type": "fast", "calo": 450,  "price": 25000,  "style": "dry",  "protein": "pork",    "method": "baked"},
    {"name": "Bánh Mì Heo Quay",          "meal_type": "fast", "calo": 500,  "price": 30000,  "style": "dry",  "protein": "pork",    "method": "baked"},
    {"name": "Bánh Mì Que Hải Phòng",     "meal_type": "fast", "calo": 180,  "price": 15000,  "style": "dry",  "protein": "pork",    "method": "baked"},
    {"name": "Xôi Gà Xé",                 "meal_type": "fast", "calo": 600,  "price": 30000,  "style": "dry",  "protein": "chicken", "method": "steamed"},
    {"name": "Xôi Mặn Thập Cẩm",         "meal_type": "fast", "calo": 650,  "price": 35000,  "style": "dry",  "protein": "mixed",   "method": "steamed"},
    {"name": "Gà Rán KFC",                "meal_type": "fast", "calo": 650,  "price": 75000,  "style": "dry",  "protein": "chicken", "method": "fried"},
    {"name": "Hamburger Bò Úc",           "meal_type": "fast", "calo": 550,  "price": 85000,  "style": "dry",  "protein": "beef",    "method": "fried"},
    {"name": "Gỏi Cuốn Tôm Thịt",        "meal_type": "fast", "calo": 200,  "price": 30000,  "style": "dry",  "protein": "mixed",   "method": "boiled"},
    {"name": "Bánh Cuốn Nóng",            "meal_type": "fast", "calo": 350,  "price": 35000,  "style": "dry",  "protein": "pork",    "method": "steamed"},
    {"name": "Cháo Sườn Sụn",             "meal_type": "fast", "calo": 400,  "price": 45000,  "style": "soup", "protein": "pork",    "method": "stewed"},
    {"name": "Cháo Trắng Hột Vịt Muối",  "meal_type": "fast", "calo": 250,  "price": 25000,  "style": "soup", "protein": "egg",     "method": "stewed"},
    {"name": "Súp Cua Óc Heo",            "meal_type": "fast", "calo": 300,  "price": 40000,  "style": "soup", "protein": "pork",    "method": "stewed"},
    {"name": "Bánh Giò Thịt Bằm",        "meal_type": "fast", "calo": 380,  "price": 25000,  "style": "dry",  "protein": "pork",    "method": "steamed"},
    {"name": "Bánh Bao Trứng Muối",      "meal_type": "fast", "calo": 360,  "price": 25000,  "style": "dry",  "protein": "egg",     "method": "steamed"},
    {"name": "Sandwich Cá Ngừ",          "meal_type": "fast", "calo": 350,  "price": 50000,  "style": "dry",  "protein": "seafood", "method": "mixed"},
    {"name": "Kimbap Truyền Thống",      "meal_type": "fast", "calo": 400,  "price": 45000,  "style": "dry",  "protein": "veg",     "method": "mixed"},
    {"name": "Tokbokki Cay Nồng",        "meal_type": "fast", "calo": 480,  "price": 55000,  "style": "soup", "protein": "veg",     "method": "stewed"},
    {"name": "Hotdog Phô Mai Hàn",       "meal_type": "fast", "calo": 520,  "price": 35000,  "style": "dry",  "protein": "pork",    "method": "fried"},
    {"name": "Takoyaki Bạch Tuộc",       "meal_type": "fast", "calo": 300,  "price": 50000,  "style": "dry",  "protein": "seafood", "method": "fried"},
    {"name": "Onigiri Cá Hồi",           "meal_type": "fast", "calo": 250,  "price": 35000,  "style": "dry",  "protein": "seafood", "method": "mixed"},
    # ── FULL / BỮA TRƯA (20 món) ─────────────────────────────
    {"name": "Cơm Tấm Sườn Bì",         "meal_type": "full", "calo": 800,  "price": 55000,  "style": "dry",  "protein": "pork",    "method": "grilled"},
    {"name": "Cơm Tấm Chả Cua",         "meal_type": "full", "calo": 780,  "price": 60000,  "style": "dry",  "protein": "seafood", "method": "steamed"},
    {"name": "Bún Bò Huế Đặc Biệt",     "meal_type": "full", "calo": 750,  "price": 65000,  "style": "soup", "protein": "beef",    "method": "stewed"},
    {"name": "Phở Bò Tái Nạm",          "meal_type": "full", "calo": 600,  "price": 60000,  "style": "soup", "protein": "beef",    "method": "boiled"},
    {"name": "Cơm Gà Xối Mỡ",          "meal_type": "full", "calo": 950,  "price": 55000,  "style": "dry",  "protein": "chicken", "method": "fried"},
    {"name": "Bún Đậu Mắm Tôm Mẹt",    "meal_type": "full", "calo": 900,  "price": 85000,  "style": "dry",  "protein": "pork",    "method": "fried"},
    {"name": "Mì Ý Carbonara",          "meal_type": "full", "calo": 880,  "price": 170000, "style": "dry",  "protein": "pork",    "method": "pan-fried"},
    {"name": "Cơm Trộn Bibimbap",       "meal_type": "full", "calo": 700,  "price": 95000,  "style": "dry",  "protein": "beef",    "method": "mixed"},
    {"name": "Ramen Tonkotsu",           "meal_type": "full", "calo": 850,  "price": 150000, "style": "soup", "protein": "pork",    "method": "stewed"},
    {"name": "Bún Chả Hà Nội",         "meal_type": "full", "calo": 650,  "price": 60000,  "style": "dry",  "protein": "pork",    "method": "grilled"},
    {"name": "Hủ Tiếu Nam Vang",        "meal_type": "full", "calo": 550,  "price": 65000,  "style": "soup", "protein": "mixed",   "method": "boiled"},
    {"name": "Cơm Niêu Cá Kho Tộ",     "meal_type": "full", "calo": 750,  "price": 110000, "style": "dry",  "protein": "seafood", "method": "stewed"},
    {"name": "Bún Riêu Cua Ốc",        "meal_type": "full", "calo": 550,  "price": 50000,  "style": "soup", "protein": "seafood", "method": "stewed"},
    {"name": "Mì Cay Cấp 7",           "meal_type": "full", "calo": 750,  "price": 80000,  "style": "soup", "protein": "beef",    "method": "boiled"},
    {"name": "Canh Chua Cá Hú",        "meal_type": "full", "calo": 650,  "price": 85000,  "style": "soup", "protein": "seafood", "method": "boiled"},
    {"name": "Cơm Rang Dưa Bò",        "meal_type": "full", "calo": 800,  "price": 60000,  "style": "dry",  "protein": "beef",    "method": "fried"},
    {"name": "Lẩu Thái 1 Người",       "meal_type": "full", "calo": 850,  "price": 120000, "style": "soup", "protein": "seafood", "method": "boiled"},
    {"name": "Sushi Set 12 Miếng",     "meal_type": "full", "calo": 550,  "price": 250000, "style": "dry",  "protein": "seafood", "method": "mixed"},
    {"name": "Mì Trộn Tên Lửa",       "meal_type": "full", "calo": 700,  "price": 45000,  "style": "dry",  "protein": "beef",    "method": "mixed"},
    {"name": "Cơm Gạo Lứt Ức Gà",     "meal_type": "full", "calo": 500,  "price": 65000,  "style": "dry",  "protein": "chicken", "method": "boiled"},
    # ── DINNER / LUXURY (20 món) ──────────────────────────────
    {"name": "Lẩu Cá Tầm Sapa",        "meal_type": "full", "calo": 1300, "price": 650000, "style": "soup", "protein": "seafood", "method": "boiled"},
    {"name": "Bò Wagyu A5 Nướng",      "meal_type": "full", "calo": 1200, "price": 1200000,"style": "dry",  "protein": "beef",    "method": "grilled"},
    {"name": "Cua Rang Me Cà Mau",     "meal_type": "full", "calo": 750,  "price": 550000, "style": "dry",  "protein": "seafood", "method": "pan-fried"},
    {"name": "Tôm Hùm Alaska Phô Mai", "meal_type": "full", "calo": 850,  "price": 950000, "style": "dry",  "protein": "seafood", "method": "baked"},
    {"name": "Lẩu Bò Nhúng Giấm",     "meal_type": "full", "calo": 1100, "price": 400000, "style": "soup", "protein": "beef",    "method": "boiled"},
    {"name": "Sườn Heo BBQ Tảng",      "meal_type": "full", "calo": 1300, "price": 450000, "style": "dry",  "protein": "pork",    "method": "grilled"},
    {"name": "Bào Ngư Sốt Dầu Hào",   "meal_type": "full", "calo": 500,  "price": 850000, "style": "soup", "protein": "seafood", "method": "stewed"},
    {"name": "Vịt Quay Bắc Kinh",      "meal_type": "full", "calo": 1500, "price": 550000, "style": "dry",  "protein": "poultry", "method": "grilled"},
    {"name": "Set Hải Sản Sashimi",    "meal_type": "full", "calo": 600,  "price": 750000, "style": "dry",  "protein": "seafood", "method": "mixed"},
    {"name": "Lẩu Gà Lá É Phú Yên",   "meal_type": "full", "calo": 1100, "price": 350000, "style": "soup", "protein": "chicken", "method": "boiled"},
    {"name": "Gà Hầm Sâm Nguyên Con", "meal_type": "full", "calo": 950,  "price": 550000, "style": "soup", "protein": "chicken", "method": "stewed"},
    {"name": "Dê Núi Nướng Mỡ Chài",  "meal_type": "full", "calo": 1400, "price": 400000, "style": "dry",  "protein": "meat",    "method": "grilled"},
    {"name": "King Crab Hấp Vang",     "meal_type": "full", "calo": 900,  "price": 1800000,"style": "dry",  "protein": "seafood", "method": "steamed"},
    {"name": "Lẩu Cá Linh Mùa Nước Nổi","meal_type":"full", "calo": 900,  "price": 300000, "style": "soup", "protein": "seafood", "method": "boiled"},
    {"name": "Gan Ngỗng Pháp Áp Chảo","meal_type": "full", "calo": 800,  "price": 1100000,"style": "dry",  "protein": "poultry", "method": "pan-fried"},
    {"name": "Set Cơm Cung Đình",      "meal_type": "full", "calo": 1000, "price": 1000000,"style": "mixed","protein": "mixed",   "method": "mixed"},
    {"name": "Bê Chao Mộc Châu",       "meal_type": "full", "calo": 1100, "price": 320000, "style": "dry",  "protein": "beef",    "method": "pan-fried"},
    {"name": "Sò Điệp Hokkaido Nướng", "meal_type": "full", "calo": 350,  "price": 800000, "style": "dry",  "protein": "seafood", "method": "grilled"},
    {"name": "Pizza Seafood Phô Mai",  "meal_type": "full", "calo": 1200, "price": 250000, "style": "dry",  "protein": "seafood", "method": "baked"},
    {"name": "Steak Thăn Lưng Bò Mỹ", "meal_type": "full", "calo": 900,  "price": 350000, "style": "dry",  "protein": "beef",    "method": "pan-fried"},
]

_SUFFIXES = ['Vip', 'Đêm', 'Phố', 'Ngon', 'Gia Truyền', 'Xịn', 'Chuẩn', 'Hot']

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


def score_dishes(target_type, target_calo, meal_period,
                 memory, max_price, profile, weather_data, sim_delivery):
    """
    Scoring + weighted random pick + delivery time injection.
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
    return send_file(os.path.join(BASE_DIR, "app.html"))


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
