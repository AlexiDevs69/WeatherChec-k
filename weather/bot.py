import os
import asyncio
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWM_API_KEY = os.getenv("OWM_API_KEY")
PORT = int(os.getenv("PORT", 8000))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{PORT}")  # ngrok url сюди
OWM_BASE = "https://api.openweathermap.org/data/2.5"

# ==================== HTML Mini App (вбудований) ====================
HTML_CONTENT = open("index.html", encoding="utf-8").read() if os.path.exists("index.html") else """
<!DOCTYPE html>
<html><body><h1>Поклади index.html поруч з bot.py</h1></body></html>
"""

# ==================== Weather helpers ====================
def transform_weather(current: dict, forecast: dict) -> dict:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    hourly = []
    for item in forecast["list"][:8]:
        dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        hourly.append({
            "time": dt.strftime("%H:%M"),
            "temp": round(item["main"]["temp"]),
            "icon": item["weather"][0]["icon"]
        })

    daily_map = {}
    for item in forecast["list"]:
        dt = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        day_key = dt.strftime("%Y-%m-%d")
        if day_key not in daily_map:
            daily_map[day_key] = {"date": dt, "temps": [], "icons": {}}
        daily_map[day_key]["temps"].append(item["main"]["temp"])
        icon = item["weather"][0]["icon"]
        daily_map[day_key]["icons"][icon] = daily_map[day_key]["icons"].get(icon, 0) + 1

    weekly = []
    for day_key, day in list(daily_map.items())[:7]:
        best_icon = max(day["icons"], key=day["icons"].get)
        label = "Today" if day_key == now.strftime("%Y-%m-%d") else day["date"].strftime("%a")
        weekly.append({
            "day": label,
            "min": round(min(day["temps"])),
            "max": round(max(day["temps"])),
            "icon": best_icon
        })

    return {
        "city": current["name"],
        "temp": round(current["main"]["temp"]),
        "feels_like": round(current["main"]["feels_like"]),
        "humidity": current["main"]["humidity"],
        "wind": round(current["wind"]["speed"] * 3.6),
        "description": current["weather"][0]["description"],
        "icon": current["weather"][0]["icon"],
        "hourly": hourly,
        "weekly": weekly
    }


async def fetch_owm(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url) as resp:
        if resp.status == 404:
            raise web.HTTPNotFound(reason="City not found")
        if resp.status != 200:
            raise web.HTTPBadGateway(reason="Weather service error")
        return await resp.json()


# ==================== Web server routes ====================
async def handle_index(request):
    """Роздаємо HTML Mini App"""
    return web.Response(
        text=HTML_CONTENT,
        content_type="text/html",
        charset="utf-8"
    )


async def handle_weather_city(request):
    """GET /weather?city=Kyiv"""
    city = request.rel_url.query.get("city", "").strip()
    if not city:
        raise web.HTTPBadRequest(reason="city param required")

    async with aiohttp.ClientSession() as session:
        current = await fetch_owm(session, f"{OWM_BASE}/weather?q={city}&appid={OWM_API_KEY}&units=metric")
        forecast = await fetch_owm(session, f"{OWM_BASE}/forecast?q={city}&appid={OWM_API_KEY}&units=metric")

    import json
    return web.Response(
        text=json.dumps(transform_weather(current, forecast), ensure_ascii=False),
        content_type="application/json"
    )


async def handle_weather_location(request):
    """GET /weather/location?lat=50&lon=30"""
    try:
        lat = float(request.rel_url.query["lat"])
        lon = float(request.rel_url.query["lon"])
    except (KeyError, ValueError):
        raise web.HTTPBadRequest(reason="lat and lon required")

    async with aiohttp.ClientSession() as session:
        current = await fetch_owm(session, f"{OWM_BASE}/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric")
        forecast = await fetch_owm(session, f"{OWM_BASE}/forecast?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric")

    import json
    return web.Response(
        text=json.dumps(transform_weather(current, forecast), ensure_ascii=False),
        content_type="application/json"
    )


async def handle_health(request):
    import json
    return web.Response(text=json.dumps({"status": "ok"}), content_type="application/json")


# ==================== CORS middleware ====================
@web.middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ==================== Telegram Bot ====================
from aiogram.client.default import DefaultBotProperties
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def get_weather_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🌤️ Відкрити погоду",
            web_app=WebAppInfo(url=f"{PUBLIC_URL}/")
        )]
    ])


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привіт! Я бот погоди.\n\n"
        "Натисни кнопку нижче щоб відкрити погоду 👇",
        reply_markup=get_weather_keyboard()
    )


@dp.message(Command("weather"))
async def cmd_weather(message: Message):
    await message.answer(
        "🌤️ Натисни щоб відкрити погоду:",
        reply_markup=get_weather_keyboard()
    )


@dp.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    data = message.web_app_data.data
    await message.answer(f"📍 Ти вибрав місто: <b>{data}</b>")


# ==================== Main ====================
async def main():
    # Створюємо веб-додаток
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", handle_index)
    app.router.add_get("/weather", handle_weather_city)
    app.router.add_get("/weather/location", handle_weather_location)
    app.router.add_get("/health", handle_health)

    # Запускаємо веб-сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"✅ Веб-сервер запущено на порту {PORT}")
    print(f"🌐 Mini App доступний: {PUBLIC_URL}/")
    print(f"🤖 Бот запускається...")

    # Запускаємо бота паралельно
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())