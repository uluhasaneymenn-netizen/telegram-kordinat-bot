import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import requests

API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("👋 Merhaba! Bana koordinat gönder (örn: 41.0082, 28.9784) ve ben sana Google Maps linki ve çevredeki mekanları göstereyim.")

@dp.message()
async def coords_to_poi(message: types.Message):
    text = message.text.replace(',', ' ').strip()
    parts = text.split()
    
    if len(parts) < 2:
        await message.reply("⚠️ Lütfen geçerli koordinat gir (örn: 41.0082 28.9784).")
        return
    
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        await message.reply("⚠️ Koordinatlar sayı formatında olmalı (örn: 41.0082 28.9784).")
        return

    # Google Maps linki
    gmaps_link = f"https://www.google.com/maps?q={lat},{lon}"
    message_text = f"📍 Google Maps: {gmaps_link}\n\n📌 Yakındaki Mekanlar:\n"

    # POI sorgusu - Overpass API
    radius = 500  # metre
    query = f"""
    [out:json];
    (
      node(around:{radius},{lat},{lon})[amenity];
      way(around:{radius},{lat},{lon})[amenity];
      relation(around:{radius},{lat},{lon})[amenity];
    );
    out center;
    """
    try:
        response = requests.get("https://overpass-api.de/api/interpreter", params={"data": query}, timeout=20)
        data = response.json()
        pois = []
        for element in data.get("elements", [])[:10]:  # ilk 10 POI
            name = element.get("tags", {}).get("name", "İsimsiz")
            amenity = element.get("tags", {}).get("amenity", "bilinmiyor")
            pois.append(f"- {name} ({amenity})")
        if not pois:
            message_text += "Yakında mekan bulunamadı."
        else:
            message_text += "\n".join(pois)
    except Exception as e:
        message_text += "POI bilgisi alınamadı."

    await message.reply(message_text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
