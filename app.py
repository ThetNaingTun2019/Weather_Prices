"""Market & Weather dashboard: current weather, oil price and gold price.

Data sources (no API keys required):
  - Weather:  Open-Meteo (https://open-meteo.com)
  - Prices:   Yahoo Finance chart API (WTI crude CL=F, Brent BZ=F, Gold GC=F)
"""
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 (WeatherPricesDashboard)"}
TIMEOUT = 10

# Locations shown by default (user can add/remove more in the UI)
DEFAULT_CITIES = ["Yangon", "Doha"]

WEATHER_CODES = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌦️"), 55: ("Dense drizzle", "🌧️"),
    56: ("Freezing drizzle", "🌧️"), 57: ("Freezing drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🌧️"), 67: ("Freezing rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "🌨️"), 75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "🌨️"), 80: ("Rain showers", "🌦️"), 81: ("Rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm with hail", "⛈️"),
    99: ("Thunderstorm with hail", "⛈️"),
}

COMMODITIES = {
    "wti": ("CL=F", "WTI Crude Oil", "USD / barrel"),
    "brent": ("BZ=F", "Brent Crude Oil", "USD / barrel"),
    "gold": ("GC=F", "Gold", "USD / troy oz"),
}


def geocode(city):
    r = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1}, headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        raise ValueError(f"City '{city}' not found")
    g = results[0]
    return g["latitude"], g["longitude"], g.get("name", city), g.get("country", ""), g.get("country_code", "")


def get_weather(city):
    lat, lon, name, country, country_code = geocode(city)
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "weather_code,wind_speed_10m,precipitation,is_day,pressure_msl",
            "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max",
        },
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    cur, units, daily = data["current"], data["current_units"], data["daily"]
    desc, icon = WEATHER_CODES.get(cur["weather_code"], ("Unknown", "❔"))
    if cur["weather_code"] in (0, 1) and not cur.get("is_day", 1):
        icon = "🌙"
    return {
        "city": name,
        "country": country,
        "country_code": country_code,
        "time": cur["time"],
        "timezone": data.get("timezone"),
        "utc_offset": data.get("utc_offset_seconds", 0),
        "description": desc,
        "icon": icon,
        "temperature": round(cur["temperature_2m"]),
        "feels_like": round(cur["apparent_temperature"]),
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "humidity": cur["relative_humidity_2m"],
        "wind": cur["wind_speed_10m"],
        "wind_unit": units["wind_speed_10m"],
        "precipitation": cur["precipitation"],
        "pressure": round(cur["pressure_msl"]),
        "uv_index": daily["uv_index_max"][0],
        "sunrise": daily["sunrise"][0][-5:],
        "sunset": daily["sunset"][0][-5:],
    }


def get_quote(symbol):
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"interval": "1d", "range": "1mo"}, headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    result = r.json()["chart"]["result"][0]
    meta = result["meta"]
    price = meta["regularMarketPrice"]
    closes = [round(c, 2) for c in result["indicators"]["quote"][0].get("close", []) if c is not None]
    # Previous session's close = second-to-last daily close
    prev = closes[-2] if len(closes) >= 2 else meta.get("chartPreviousClose")
    change = price - prev if prev else 0.0
    pct = (change / prev * 100) if prev else 0.0
    return {
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(pct, 2),
        "day_high": meta.get("regularMarketDayHigh"),
        "day_low": meta.get("regularMarketDayLow"),
        "history": closes,
        "updated": datetime.fromtimestamp(meta["regularMarketTime"]).strftime("%d %b %Y, %H:%M"),
    }


def get_prices():
    prices = {}
    for key, (symbol, label, unit) in COMMODITIES.items():
        try:
            prices[key] = {"label": label, "symbol": symbol, "unit": unit, **get_quote(symbol)}
        except Exception as e:  # keep the page working if one quote fails
            prices[key] = {"label": label, "symbol": symbol, "unit": unit, "error": str(e)}
    return prices


@app.route("/")
def index():
    return render_template("index.html", default_cities=DEFAULT_CITIES)


@app.route("/api/weather")
def api_weather():
    city = request.args.get("city", "").strip() or DEFAULT_CITIES[0]
    try:
        return jsonify(get_weather(city))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/prices")
def api_prices():
    return jsonify(get_prices())


if __name__ == "__main__":
    app.run(debug=True)
