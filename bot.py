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
        pois.append(f"- {name} ({amenity}) ~{dist} m uzaklıkta")
    if not pois:
        message_text += "Yakında mekan bulunamadı."
    else:
        message_text += "\n".join(pois)
except Exception as e:
    message_text += "POI bilgisi alınamadı."
