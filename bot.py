import asyncio
import os
import requests
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from math import radians, cos, sin, sqrt, atan2

# Token'ı doğrudan yazmak yerine ortam değişkeninden al (güvenli)
API_TOKEN = os.getenv("API_TOKEN", "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

AMENITY_TR = {
    "cafe": "Kafe",
    "school": "Okul",
    "restaurant": "Restoran",
    "hospital": "Hastane",
    "clinic": "Polikilinik",
    "bank": "Banka",
    "pharmacy": "Eczane",
    "parking": "Otopark",
    "bar": "Bar",
    "supermarket": "Süpermarket",
}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return round(R * 2 * atan2(sqrt(a), sqrt(1 - a)))

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("👋 Merhaba! Bana koordinat gönder (örn: 41.0082, 28.9784) ve sana konum ve yakındaki mekanları göstereyim.")

@dp.message()
async def coords_to_maps(message: types.Message):
    text = message.text.replace(',', ' ').strip()
    parts = text.split()
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except:
        await message.reply("❌ Geçerli bir koordinat giriniz. Örn: 41.0082, 28.9784")
        return

    msg = f"Tesisatın yaklaşık en yakın konumu ve çevresinde bulunan yakın yapılar aşağıda belirtilmiştir;\n\n"
    msg += f"📍 Google Maps Linki: https://www.google.com/maps?q={lat},{lon}\n\n"

    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse", params={
            "lat": lat, "lon": lon, "format": "json", "addressdetails": 1
        }, timeout=10)
        addr = r.json().get("address", {})
        parts = []
        for key in ("suburb", "neighbourhood", "road", "house_number", "city_district", "county", "city"):
            if addr.get(key):
                parts.append(addr[key])
        if parts:
            msg += "🏠 Adres:\n" + ", ".join(parts) + "\n\n"
    except:
        pass

    radius = 500
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
        res = requests.get("https://overpass-api.de/api/interpreter", params={"data": query}, timeout=20)
        data = res.json()
        pois = []
        for el in data.get("elements", []):
            name = el.get("tags", {}).get("name")
            if not name:
                continue
            amenity = AMENITY_TR.get(el.get("tags", {}).get("amenity", ""), "bilinmiyor")
            poi_lat = el.get("lat") or el.get("center", {}).get("lat")
            poi_lon = el.get("lon") or el.get("center", {}).get("lon")
            if poi_lat and poi_lon:
                dist = haversine(lat, lon, poi_lat, poi_lon)
                pois.append((dist, f"- {name} ({amenity}) ~{dist} m uzaklıkta"))
        if pois:
            pois.sort(key=lambda x: x[0])
            msg += "📌 Yakındaki Mekanlar:\n" + "\n".join(p[1] for p in pois[:7])
    except:
        pass

    await message.reply(msg)

async def main():
    loop = asyncio.get_event_loop()

    # Botu başlat
    loop.create_task(dp.start_polling(bot))

    # Basit web server (platform port istiyor diye)
    async def handle(request):
        return web.Response(text="✅ Bot aktif ve çalışıyor")

    app = web.Application()
    app.router.add_get("/", handle)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
