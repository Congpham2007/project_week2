(function () {
  const API_BASE = window.location.port === "5000" ? "" : "http://127.0.0.1:5000";

  const STORAGE_KEYS = {
    weather: "smart_food_weather",
    recommend: "smart_food_recommend",
    recommendPayload: "smart_food_recommend_payload",
    plan: "smart_food_plan",
    selectedDish: "smart_food_selected_dish"
  };

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      mode: "cors",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    if (!response.ok) {
      throw new Error(`API ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  function setStored(key, value) {
    sessionStorage.setItem(key, JSON.stringify(value));
  }

  function getStored(key, fallback = null) {
    try {
      const raw = sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function weatherIcon(weather) {
    if (!weather) return "☀️";
    if (["Rain", "Rainy", "Drizzle", "Thunderstorm"].includes(weather)) return "🌧️";
    if (["Clouds", "Cloudy", "Mist"].includes(weather)) return "⛅";
    return "☀️";
  }

  function formatPrice(price) {
    return `${Number(price || 0).toLocaleString("vi-VN")}đ`;
  }

  function formatDistance(distance) {
    const value = Number(distance || 0);
    return `${value.toFixed(value < 1 ? 1 : 1)}km`;
  }

  function buildMatch(rank, matchFromApi) {
    if (typeof matchFromApi === "number") return `${Math.round(matchFromApi)}% Match`;
    const presets = [98, 94, 91, 88, 84, 80, 76, 72];
    return `${presets[Math.min(rank, presets.length - 1)]}% Match`;
  }

  window.smartFoodApi = {
    API_BASE,
    STORAGE_KEYS,
    request,
    getWeather: () => request("/api/weather", { method: "GET", headers: {} }),
    getRecommend: (payload) => request("/api/recommend", { method: "POST", body: JSON.stringify(payload) }),
    getPlan: (payload) => request("/api/plan", { method: "POST", body: JSON.stringify(payload) }),
    getMap: (payload) => request("/api/map", { method: "POST", body: JSON.stringify(payload) })
  };

  window.smartFoodStore = {
    setStored,
    getStored
  };

  window.smartFoodUtils = {
    weatherIcon,
    formatPrice,
    formatDistance,
    buildMatch
  };
})();
