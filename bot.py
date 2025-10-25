import logging
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
import asyncio
import re

# 🟢 Telegram Bot Token
API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

# 🗺️ Mapbox Token
MAPBOX_TOKEN = "pk.3ea4c2c2a9f99983304d9c7ddc358c63"

# Log ayarları
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# 🔹 /start komutu
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Merhaba! Bana bir koordinat gönder (örnek: `41.0082, 28.9784`)\n"
        "Ben de sana harita görüntüsü ve Google linki atayım 🌍",
        parse_mode="Markdown"
    )

# 🔹 Koordinat algılama
@dp.message()
async def handle_coordinate(message: Message):
    text = message.text.strip()

    # 📍 Her türlü formatı yakalamak için regex (41.0082,28.9784 / 41.0082 28.9784)
    match = re.match(r"([-+]?\d{1,2}\.\d+)[,\s]+([-+]?\d{1,3}\.\d+)", text)

    if not match:
        await message.answer("⚠️ Lütfen geçerli bir koordinat gir (örnek: `41.0082, 28.9784`).")
        return

    lat = float(match.group(1))
    lon = float(match.group(2))

    # 🗺️ Mapbox harita görüntüsü
    map_url = (
        f"https://api.mapbox.com/styles/v1/mapbox/streets-v11/static/"
        f"pin-s+ff0000({lon},{lat})/{lon},{lat},14,0/600x400"
        f"?access_token={MAPBOX_TOKEN}"
    )

    # 🌍 Google Maps linki
    google_url = f"https://maps.google.com/?q={lat},{lon}"

    # 🖼️ Harita fotoğrafını gönder
    await message.answer_photo(
        map_url,
        caption=f"📍 Koordinat: {lat}, {lon}\n🔗 [Google Maps'te aç]({google_url})",
        parse_mode="Markdown"
    )

# 🔹 Botu başlat
async def main():
    print("🤖 Bot çalışıyor...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
