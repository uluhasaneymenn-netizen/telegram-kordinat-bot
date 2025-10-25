import asyncio
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from math import radians, cos, sin, sqrt, atan2

API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Amenity çeviri sözlüğü
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

# Haversine mesafe hesaplama
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # metre
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return round(R * c)

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("👋 Merhaba! Bana koordinat gönder (örn: 41.0082, 28.9784) ve sana konum ve yakındaki mekanları göstereyim.")

@dp.message()
async def coords_to_maps(message: types.Message):
    text = message.text.replace(',', ' ').strip()
    parts = text.split()

    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except:
        await message.reply("❌ Geçerli bir koordinat giriniz. Örn: 41.0082, 28.9784")
        return

    # Başlangıç mesajı
    message_text = "Tesisatın yaklaşık en yakın konumu ve çevresinde bulunan yakın yapılar aşağıda belirtilmiştir;\n\n"
    message_text += f"📍 Google Maps Linki: https://www.google.com/maps?q={lat},{lon}\n\n"

    # Adres bilgisi (Nominatim OpenStreetMap)
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse", params={
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1
        }, timeout=10)
        addr = r.json().get("address", {})
        address_parts = []
        if addr.get("suburb") or addr.get("neighbourhood"):
            address_parts.append(addr.get("suburb") or addr.get("neighbourhood"))
        if addr.get("road"):
            address_parts.append(addr.get("road"))
        if addr.get("house_number"):
            address_parts.append(addr.get("house_number"))
        if addr.get("city_district") or addr.get("county") or addr.get("city"):
            address_parts.append(addr.get("city_district") or addr.get("county") or addr.get("city"))
        if address_parts:
            message_text += "🏠 Adres:\n" + ", ".join(address_parts) + "\n\n"
    except:
        pass  # Adres alınamazsa atla

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
        for element in data.get("elements", []):
            name = element.get("tags", {}).get("name")
            if not name:
                continue  # isimsiz mekanları atla
            amenity = element.get("tags", {}).get("amenity", "bilinmiyor")
            amenity_tr = AMENITY_TR.get(amenity, amenity)
            if "lat" in element and "lon" in element:
                poi_lat = element["lat"]
                poi_lon = element["lon"]
            elif "center" in element:
                poi_lat = element["center"]["lat"]
                poi_lon = element["center"]["lon"]
            else:
                continue  # adres yoksa atla
            dist = haversine(lat, lon, poi_lat, poi_lon)
            pois.append((dist, f"- {name} ({amenity_tr}) ~{dist} m uzaklıkta"))

        if pois:
            # Mesafeye göre sırala ve en fazla 7 tane al
            pois.sort(key=lambda x: x[0])
            message_text += "📌 Yakındaki Mekanlar:\n" + "\n".join([p[1] for p in pois[:7]])
    except:
        pass  # POI alınamazsa atla

    await message.reply(message_text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
