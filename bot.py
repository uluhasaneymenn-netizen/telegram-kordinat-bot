import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

# 🔐 Telegram Token
API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

# 🗺️ Mapbox Token
MAPBOX_TOKEN = "pk.3ea4c2c2a9f99983304d9c7ddc358c63"

# Logging
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Merhaba! Bana bir koordinat gönder (örnek: `41.0082, 28.9784`)\n"
        "Ben de sana harita görüntüsü ve Google linki atayım 🌍",
        parse_mode="Markdown"
    )


@dp.message()
async def handle_coordinate(message: Message):
    text = message.text.strip().replace("°", "").replace("’", "").replace("‘", "")
    text = text.replace(",", " ").replace("  ", " ")
    parts = text.split()

    # 🧠 Koordinatları kontrol et
    if len(parts) < 2:
        await message.answer("⚠️ Lütfen geçerli bir koordinat gir (örnek: `41.0082, 28.9784`).")
        return

    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        await message.answer("⚠️ Sayısal formatta bir koordinat girmen gerekiyor (örnek: `41.0082, 28.9784`).")
        return

    # 🗺️ Mapbox statik harita URL’si
    map_url = (
        f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/"
        f"pin-s+ff0000({lon},{lat})/{lon},{lat},14,0/600x400"
        f"?access_token={MAPBOX_TOKEN}"
    )

    google_url = f"https://maps.google.com/?q={lat},{lon}"

    # 🖼️ Haritayı gönder
    await message.answer_photo(
        map_url,
        caption=f"📍 Koordinat: {lat}, {lon}\n🔗 [Google Maps'te aç]({google_url})",
        parse_mode="Markdown"
