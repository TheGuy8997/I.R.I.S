# weather.py

import requests
import time
import json

# =========================
# CONFIG
# =========================
OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"
IP_GEOLOCATION_API = "http://ip-api.com/json/"
WEATHER_CACHE = {"data": None, "timestamp": 0, "location": None}
CACHE_DURATION = 900  # 15 minutes

# =========================
# LOCATION FUNCTIONS
# =========================

def get_user_location():
    """Get user location via IP geolocation."""
    try:
        response = requests.get(IP_GEOLOCATION_API, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "success":
            return {
                "latitude": data.get("lat"),
                "longitude": data.get("lon"),
                "city": data.get("city", "Unknown"),
                "region": data.get("regionName", ""),
                "country": data.get("country", "")
            }
    except Exception as e:
        print(f"[LOCATION ERROR] {e}")
    
# Fallback to Rochester, MN
    return {
    "latitude": 44.0121,
    "longitude": -92.4802,
    "city": "Rochester",
    "region": "MN",
    "country": "USA"
}

# =========================
# WEATHER DATA FUNCTIONS
# =========================

def get_detailed_weather(location=None):
    """Get detailed weather forecast from Open-Meteo API."""
    # Get location if not provided
    if location is None:
        location = get_user_location()
    
    # Check cache first
    current_time = time.time()
    cache_key = f"{location['latitude']},{location['longitude']}"
    
    if (WEATHER_CACHE["data"] is not None and 
        WEATHER_CACHE["location"] == cache_key and
        current_time - WEATHER_CACHE["timestamp"] < CACHE_DURATION):
        return WEATHER_CACHE["data"]
    
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,cloud_cover",
        "hourly": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m,precipitation_probability,precipitation,rain,showers,snowfall,cloud_cover,visibility",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_sum,rain_sum,showers_sum,snowfall_sum,precipitation_hours,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max",
        "temperature_unit": "fahrenheit",
        "windspeed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 7
    }
    
    try:
        response = requests.get(OPEN_METEO_API, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Add location info to response
        data["location_info"] = location
        
        # Cache the result
        WEATHER_CACHE["data"] = data
        WEATHER_CACHE["timestamp"] = current_time
        WEATHER_CACHE["location"] = cache_key
        
        return data
    except Exception as e:
        print(f"[WEATHER ERROR] {e}")
        return None

def get_weather_summary():
    """Get a summary of current weather for quick responses."""
    weather_data = get_detailed_weather()
    if not weather_data:
        return "Weather data unavailable"
    
    current = weather_data.get("current", {})
    location_info = weather_data.get("location_info", {})
    
    temp = current.get("temperature_2m", "unknown")
    wind = current.get("wind_speed_10m", "unknown")
    humidity = current.get("relative_humidity_2m", "unknown")
    weather_code = current.get("weather_code", 0)
    apparent_temp = current.get("apparent_temperature", temp)
    
    # Location info
    city = location_info.get("city", "your area")
    
    # Simple weather code mapping
    weather_descriptions = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "foggy",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        71: "slight snow fall",
        73: "moderate snow fall",
        75: "heavy snow fall",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        95: "thunderstorm",
    }
    
    description = weather_descriptions.get(weather_code, "unknown conditions")
    
    return {
        "location": city,
        "temperature": temp,
        "apparent_temperature": apparent_temp,
        "weather": description,
        "wind_speed": wind,
        "humidity": humidity,
        "full_data": weather_data
    }

# =========================
# WEATHER QUERY INTERFACE FOR GEMMA
# =========================

def get_weather_context():
    """Get weather context for Gemma/Ollama prompts."""
    summary = get_weather_summary()
    if isinstance(summary, str):
        return summary
    
    daily = summary["full_data"].get("daily", {})
    dates = daily.get("time", [])[:3]  # Next 3 days
    temps_max = daily.get("temperature_2m_max", [])[:3]
    temps_min = daily.get("temperature_2m_min", [])[:3]
    weather_codes = daily.get("weather_code", [])[:3]
    
    # Weather code descriptions for forecast
    weather_descriptions = {
        0: "clear", 1: "clear", 2: "partly cloudy", 3: "overcast",
        45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
        61: "light rain", 63: "rain", 65: "heavy rain",
        71: "light snow", 73: "snow", 75: "heavy snow",
        80: "light showers", 81: "showers", 82: "heavy showers",
        95: "thunderstorms"
    }
    
    forecast_lines = []
    for i in range(len(dates)):
        if i < len(temps_max) and i < len(temps_min) and i < len(weather_codes):
            desc = weather_descriptions.get(weather_codes[i], "unknown")
            forecast_lines.append(f"{dates[i]}: {desc}, high {temps_max[i]}°C, low {temps_min[i]}°C")
    
    forecast_text = "\n".join(forecast_lines) if forecast_lines else "Forecast unavailable"
    
    context = f"""Current weather in {summary['location']}:
Temperature: {summary['temperature']}°Fahrenheit (feels like {summary['apparent_temperature']}°Fahrenheit)
Conditions: {summary['weather']}
Wind: {summary['wind_speed']} miles per hour
Humidity: {summary['humidity']}%

3-day forecast:
{forecast_text}"""
    
    return context

def is_weather_question(text):
    """Check if text is asking about weather."""
    text_lower = text.lower()
    weather_keywords = [
        "weather", "temperature", "rain", "sun", "cloud", "wind", 
        "snow", "forecast", "cold", "hot", "warm", "chilly", 
        "precipitation", "humidity", "climate", "coat", "temps", "highs",
"lows", "storms", "clouds", "sunny", ]
    return any(keyword in text_lower for keyword in weather_keywords)

def handle_weather_command(text):
    """Handle weather-related voice commands - simplified for direct use."""
    if is_weather_question(text):
        summary = get_weather_summary()
        if isinstance(summary, str):
            return summary
        
        return f"The current weather in {summary['location']} is {summary['weather']} with a temperature of {summary['temperature']}°Fahrenheit, wind speed of {summary['wind_speed']} miles per hour, and humidity at {summary['humidity']}%."
    
    return None
