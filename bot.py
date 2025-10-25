import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from math import radians, cos, sin, asin, sqrt

# Telegram Bot Token
API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Haversine ile iki koordinat arası mesafe hesaplama
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # metre
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    return R * c

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Merhaba! Bana koordinat gönder (örn: 41.0082, 28.9784) "
        "ve ben sana Google Maps linki ve yakındaki mekanları vereyim."
    )

@dp.message()
async def coords_to_maps(message: types.Message):
    text = message.text.replace(',', ' ').strip()
    parts = text.split()

    try:
        lat = float(parts[0])
        lon = float(parts[1])

        # Google Maps linki
        link = f"https://www.google.com/maps?q={lat},{lon}"
        message_text = f"📍 Google Maps: {link}\n\nYakındaki Mekanlar:\n"

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
            response = requests.get(
                "https://overpass-api.de/api/interpreter",
                params={"data": query},
                timeout=20
            )
            data = response.json()
            pois = []

            for element in data.get("elements", []):
                name = element.get("tags", {}).get("name")
                if not name:  # isimsizse atla
                    continue
                amenity = element.get("tags", {}).get("amenity", "bilinmiyor")
                if "lat" in element and "lon" in element:
                    poi_lat = element["lat"]
                    poi_lon = element["lon"]
                elif "center" in element:
                    poi_lat = element["center"]["lat"]
                    poi_lon = element["center"]["lon"]
                else:
                    continue
                dist = haversine(lat, lon, poi_lat, poi_lon)
                pois.append(f"- {name} ({amenity}) ~{dist:.0f} m uzaklıkta")

            if not pois:
                message_text += "Yakında mekan bulunamadı."
            else:
                message_text += "\n".join(pois)
        except Exception:
            message_text += "POI bilgisi alınamadı."

        await message.reply(message_text)

    except:
        await message.reply("❌ Lütfen geçerli bir koordinat gönder (örn: 41.0082, 28.9784).")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
