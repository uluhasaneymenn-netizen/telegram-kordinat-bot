# -*- coding: utf-8 -*-
"""
Kirpik Dünyası – Koordinat Algılama Botu (Dayanıklı + Gelişmiş OCR)
Sıra: EXIF GPS → QR → OCR [PaddleOCR ➜ EasyOCR ➜ Tesseract] → Caption/Dosya adı
Özellikler:
- TR için akıllı işaret düzeltmesi (OCR başa '-' yapıştırırsa).
- OpenCV ile çok-aşamalı ön-işleme ve çok denemeli OCR.
- Yandex Static Maps, Google/Apple linkleri, (opsiyonel) Nominatim reverse geocode.
- (Yeni) Overpass ile yakındaki mekanları listeleme.
- Polling’de bağlantı kesilmesine karşı otomatik yeniden bağlanma ve oturum yenileme.
"""

import os, sys, re, time, logging
from io import BytesIO
from datetime import datetime
from math import radians, cos, sin, sqrt, atan2  # <-- yeni

import requests
import telebot
from telebot import apihelper
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ExifTags
import qrcode

# ============= LOGGING =============
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("kirpik-ocr-bot")

# ============= AYARLAR =============
TOKEN = os.environ.get("TG_BOT_TOKEN", None)
if not TOKEN:
    # İstersen burada direkt token da yazabilirsin (güvenli değil; tercihen ortam değişkeni kullan)
    TOKEN = "8297805648:AAFlFfJrNNbBXCPU91nuvQSc0Z_ZK7L4PCM"

if not re.match(r'^\d+:[A-Za-z0-9_-]+$', TOKEN or ""):
    raise SystemExit("❌ Hatalı token. TG_BOT_TOKEN ortam değişkenini gerçek bot tokenı ile ayarla.")

USE_ONLINE_REVERSE_GEOCODE = True
NOMINATIM_UA = os.environ.get("NOMINATIM_UA", "kirpik-dunyasi-bot@example.com")
YANDEX_LANG = "tr_TR"; YANDEX_ZOOM = 17; YANDEX_SIZE = (600, 400); YANDEX_PT_STYLE = "pm2rdm"
NOMINATIM_DELAY = 1.0

# (Yeni) Yakındaki mekanlar özelliği ayarları
USE_NEARBY_POIS = True
NEARBY_RADIUS = 500       # metre
NEARBY_LIMIT  = 7         # en fazla kaç mekan gösterilecek

# Türkiye ipucu (yanlış '-' gelirse düzeltmek için). İstemezsen None yap.
REGION_HINT = "TR"

# TeleBot init
bot = telebot.TeleBot(TOKEN, parse_mode=None)

# Webhook kapat (polling ile çakışmasın)
try:
    bot.remove_webhook()
except Exception:
    pass

# Requests session TTL (destekleniyor olabilir)
try:
    apihelper.SESSION_TIME_TO_LIVE = 300  # saniye
except Exception:
    pass

# ✅ Sürüm uyumlusu timeout ayarı:
try:
    if hasattr(apihelper, "set_default_timeout"):
        apihelper.set_default_timeout((10, 70))      # (connect, read)
    else:
        apihelper.DEFAULT_TIMEOUT = (10, 70)         # Eski sürümler
except Exception:
    pass

# ============= OPSİYONEL: QR =============
try:
    from pyzbar.pyzbar import decode as zbar_decode
except Exception:
    zbar_decode = None

# ============= OCR MOTORLARI =============
PADDLE_AVAILABLE = False; paddle_ocr = None
try:
    from paddleocr import PaddleOCR
    paddle_ocr = PaddleOCR(use_angle_cls=True, lang='en', use_gpu=False, show_log=False)
    PADDLE_AVAILABLE = True
    log.info("PaddleOCR aktif.")
except Exception as e:
    log.info(f"PaddleOCR pasif: {e}")

EASYOCR_AVAILABLE = False; easy_reader = None
try:
    import easyocr
    easy_reader = easyocr.Reader(['tr', 'en'], gpu=False, verbose=False)
    EASYOCR_AVAILABLE = True
    log.info("EasyOCR aktif.")
except Exception as e:
    log.info(f"EasyOCR pasif: {e}")

TESS_AVAILABLE = False
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = os.environ.get(
        "TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
    TESS_AVAILABLE = True
    log.info("Tesseract yedek olarak aktif.")
except Exception as e:
    log.info(f"Tesseract pasif: {e}")

# ============= REGEXLER =============
COORD_PATTERNS = [
    r'(?<!\d)([-+]?\d{1,2}\.\d{4,8})\s*[,;\s]\s*([-+]?\d{1,3}\.\d{4,8})',
    r'@([-+]?\d{1,2}\.\d{4,8})\s*,\s*([-+]?\d{1,3}\.\d{4,8})',
    r'(-?\d{1,2}\.\d{4,8})[^0-9-]+(-?\d{1,3}\.\d{4,8})',
]

# ============= YAKIN MEKANLAR (Yeni) =============
AMENITY_TR = {
    "cafe": "Kafe",
    "school": "Okul",
    "restaurant": "Restoran",
    "hospital": "Hastane",
    "clinic": "Poliklinik",
    "bank": "Banka",
    "pharmacy": "Eczane",
    "parking": "Otopark",
    "bar": "Bar",
    "supermarket": "Süpermarket",
}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return round(R * 2 * atan2(sqrt(a), sqrt(1 - a)))

def fetch_nearby_pois(lat, lon, radius=NEARBY_RADIUS, limit=NEARBY_LIMIT, timeout=25):
    """
    Overpass'tan amenity POI'leri çeker, mesafeye göre sıralar, metin listesi döner.
    Kamu servisi olduğundan fazla isteklerde rate-limit olabilir.
    """
    query = f"""
    [out:json][timeout:25];
    (
      node(around:{radius},{lat},{lon})[amenity];
      way(around:{radius},{lat},{lon})[amenity];
      relation(around:{radius},{lat},{lon})[amenity];
    );
    out center;
    """
    try:
        r = requests.get(
            "https://overpass-api.de/api/interpreter",
            params={"data": query},
            headers={"User-Agent": "KirpikDunyasiBot/1.0 (overpass)"},
            timeout=timeout
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning(f"Overpass isteği başarısız: {e}")
        return []

    pois = []
    for el in data.get("elements", []):
        tags = el.get("tags", {}) or {}
        name = tags.get("name")
        if not name:
            continue
        amenity = AMENITY_TR.get(tags.get("amenity", ""), "bilinmiyor")
        poi_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        poi_lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if poi_lat is None or poi_lon is None:
            continue
        dist = haversine(lat, lon, float(poi_lat), float(poi_lon))
        pois.append((dist, f"- {name} ({amenity}) ~{dist} m"))
    pois.sort(key=lambda x: x[0])
    return [text for _, text in pois[:limit]]

# ============= YARDIMCILAR =============
def generate_qr(url: str) -> Image.Image:
    qr = qrcode.QRCode(box_size=4, border=1)
    qr.add_data(url); qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

def dms_to_deg(dms, ref):
    try:
        deg = dms[0][0]/dms[0][1]; mins = dms[1][0]/dms[1][1]; secs = dms[2][0]/dms[2][1]
        val = deg + mins/60.0 + secs/3600.0
        return -val if ref in ("S","W") else val
    except Exception:
        return None

def extract_coords_from_exif(img: Image.Image):
    try:
        exif = img._getexif()
        if not exif: return None
        gps_tag = next((k for k, v in ExifTags.TAGS.items() if v == "GPSInfo"), None)
        if gps_tag is None or gps_tag not in exif: return None
        gps = exif[gps_tag]
        gps_data = {ExifTags.GPSTAGS.get(k, k): gps[k] for k in gps}
        lat = dms_to_deg(gps_data.get("GPSLatitude"), gps_data.get("GPSLatitudeRef"))
        lon = dms_to_deg(gps_data.get("GPSLongitude"), gps_data.get("GPSLongitudeRef"))
        if lat is not None and lon is not None:
            return (lat, lon, "exif")
    except Exception:
        pass
    return None

def _normalize_text(text: str) -> str:
    text = (text or "")
    text = text.replace("–","-").replace("—","-").replace("−","-")
    text = re.sub(r"(?m)^\s*-\s*", "", text)  # satır başı madde imi "- " temizle
    return text

def _maybe_fix_sign_by_region(lat: float, lon: float):
    if REGION_HINT == "TR":
        LAT_MIN, LAT_MAX = 35.0, 43.5; LON_MIN, LON_MAX = 25.0, 45.0
        # Olduğu haliyle TR içindeyse bırak
        if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX: return lat, lon
        # Mutlak değerleri TR içindeyse işaretleri düzelt
        a,b = abs(lat), abs(lon)
        if LAT_MIN <= a <= LAT_MAX and LON_MIN <= b <= LON_MAX: return a, b
        # Sık: sadece enlem negatif
        if lat < 0 and LAT_MIN <= abs(lat) <= LAT_MAX and LON_MIN <= lon <= LON_MAX: return abs(lat), lon
        # Nadir: sadece boylam negatif
        if lon < 0 and LAT_MIN <= lat <= LAT_MAX and LON_MIN <= abs(lon) <= LON_MAX: return lat, abs(lon)
    return lat, lon

def extract_coords_from_text(text: str):
    if not text: return None
    text = _normalize_text(text)
    cands = []
    for pat in COORD_PATTERNS:
        for m in re.finditer(pat, text):
            try:
                lat = float(m.group(1)); lon = float(m.group(2))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    cands.append((lat, lon))
            except Exception:
                pass
    if not cands: return None
    best = None
    if REGION_HINT == "TR":
        for lat, lon in cands:
            fl, flon = _maybe_fix_sign_by_region(lat, lon)
            if 35.0 <= fl <= 43.5 and 25.0 <= flon <= 45.0:
                best = (fl, flon); break
    if best is None:
        lat, lon = cands[0]; best = _maybe_fix_sign_by_region(lat, lon)
    return (best[0], best[1], "text")

def extract_coords_from_qr(img: Image.Image):
    if zbar_decode is None: return None
    try:
        for r in zbar_decode(img):
            data = r.data.decode("utf-8", errors="ignore")
            c = extract_coords_from_text(data)
            if c: return (c[0], c[1], "qr")
    except Exception:
        pass
    return None

# ---- OpenCV ön-işleme varyantları ----
import cv2, np as _np  # NumPy ismini çakıştırmamak için alias
import numpy as np
def _prep_variants(pil_img: Image.Image):
    img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variants = []

    def add(var):
        big = cv2.resize(var, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        variants.append(big)

    # 1) CLAHE + bilateral + sharpen
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(gray)
    blur = cv2.bilateralFilter(clahe, 7, 75, 75)
    sharp = cv2.addWeighted(blur, 1.5, cv2.GaussianBlur(blur, (0,0), 1.0), -0.5, 0)
    add(sharp)

    # 2) Adaptif threshold (pozitif & negatif)
    th = cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 10)
    add(th); add(255 - th)

    # 3) Morfoloji
    kernel = np.ones((3,3), np.uint8)
    opened = cv2.morphologyEx(sharp, cv2.MORPH_OPEN, kernel, iterations=1)
    add(opened)

    # 4) Yüksek kontrast
    high = cv2.convertScaleAbs(sharp, alpha=1.8, beta=0)
    add(high)

    return variants

# ---- OCR arayüzleri ----
def _ocr_paddle(img_bgr: np.ndarray) -> str | None:
    if not PADDLE_AVAILABLE: return None
    try:
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        result = paddle_ocr.ocr(rgb, cls=True)
        lines = []
        for page in result or []:
            for item in page:
                txt = item[1][0]
                if txt: lines.append(txt)
        return "\n".join(lines) if lines else None
    except Exception:
        return None

def _ocr_easy(img_bgr: np.ndarray) -> str | None:
    if not EASYOCR_AVAILABLE or easy_reader is None: return None
    try:
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        lines = easy_reader.readtext(rgb, detail=0, paragraph=True)
        return "\n".join(lines) if lines else None
    except Exception:
        return None

def _ocr_tess(img_bgr: np.ndarray) -> str | None:
    if not TESS_AVAILABLE: return None
    try:
        from PIL import Image as _PIL
        pil = _PIL.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789.,-+'
        return pytesseract.image_to_string(pil, lang="eng+tur", config=config)
    except Exception:
        return None

def extract_coords_with_ocr(pil_img: Image.Image):
    variants = _prep_variants(pil_img)
    engines = [("paddle", _ocr_paddle), ("easyocr", _ocr_easy), ("tesseract", _ocr_tess)]
    for name, engine in engines:
        if (name == "paddle" and not PADDLE_AVAILABLE) or (name == "easyocr" and not EASYOCR_AVAILABLE) or (name == "tesseract" and not TESS_AVAILABLE):
            continue
        for v in variants:
            text = engine(v)
            if text:
                c = extract_coords_from_text(text)
                if c: return c
    return None

def reverse_geocode(lat, lon):
    if not USE_ONLINE_REVERSE_GEOCODE: return None
    try:
        time.sleep(NOMINATIM_DELAY)
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"format":"jsonv2","lat":f"{lat}","lon":f"{lon}","zoom":18,"addressdetails":1}
        headers = {"User-Agent": f"KirpikDunyasiBot/1.0 ({NOMINATIM_UA})"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        js = resp.json()
        return js.get("display_name")
    except Exception:
        return None

def get_address_simulation(lat, lon):
    if 37.017 <= lat <= 37.019 and 35.286 <= lon <= 35.288:
        return "Mahalle: 100. Yıl, Sokak: Atatürk Cd., İlçe: Seyhan, İl: Adana"
    elif 37.020 <= lat <= 37.022 and 35.285 <= lon <= 35.287:
        return "Mahalle: Kurtuluş, Sokak: Cumhuriyet Blv., İlçe: Seyhan, İl: Adana"
    elif 37.024 <= lat <= 37.026 and 35.277 <= lon <= 35.279:
        return "Mahalle: Reşatbey, Sokak: Ziyapaşa Blv., İlçe: Seyhan, İl: Adana"
    return "Adres (offline): bulunamadı"

def _safe_text_bbox(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    try:
        x0,y0,x1,y1 = draw.textbbox((0,0), text, font=font); return x1-x0, y1-y0
    except Exception:
        lines = text.splitlines() or [text]; max_w=0; total_h=0
        for line in lines:
            try:
                w,h = draw.textsize(line, font=font)
            except Exception:
                w,h = (len(line)*8,16)
            max_w=max(max_w,w); total_h+=h
        return max_w,total_h

def generate_map_image(lat, lon):
    url = ("https://static-maps.yandex.ru/1.x/"
           f"?ll={lon},{lat}&z={YANDEX_ZOOM}&size={YANDEX_SIZE[0]},{YANDEX_SIZE[1]}"
           f"&l=map&lang={YANDEX_LANG}&pt={lon},{lat},{YANDEX_PT_STYLE}")
    try:
        r = requests.get(url, timeout=15); r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None

    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        try: font = ImageFont.truetype("DejaVuSans.ttf", 16)
        except Exception: font = ImageFont.load_default()

    text = f"{lat:.6f}, {lon:.6f}\n{datetime.now().strftime('%Y-%m-%d')}"
    pad=6; tw,th=_safe_text_bbox(draw,text,font)
    bg=Image.new("RGBA",(tw+pad*2,th+pad*2),(255,255,255,200)); img.paste(bg,(10,10),bg)
    draw.text((10+pad,10+pad), text, fill="black", font=font)

    link = f"https://www.google.com/maps?q={lat},{lon}"
    qr_img = generate_qr(link).convert("RGBA")
    img.paste(qr_img, (img.width-qr_img.width-10, img.height-qr_img.height-10), qr_img)

    buf = BytesIO(); img.save(buf, format="PNG"); buf.name="map.png"; buf.seek(0)
    return buf

def resolve_coords_from_any(img: Image.Image, caption_text: str = None, file_name: str = None):
    for fn in (extract_coords_from_exif, extract_coords_from_qr, extract_coords_with_ocr):
        c = fn(img)
        if c: return c
    for text in (caption_text, file_name):
        if text:
            c = extract_coords_from_text(text)
            if c: return c
    return None

# ============= HANDLERLAR =============
@bot.message_handler(commands=["start","help"])
def start(message):
    bot.reply_to(
        message,
        "Koordinat gönder (örn: `37.045054, 35.310732`) **veya** fotoğraf yükle.\n"
        "- EXIF, QR, OCR [PaddleOCR→EasyOCR→Tesseract] ve açıklamadan algılar.\n"
        "- Başarılı olursa haritalı görsel + link + adres + (yakın POI'ler) döner.",
        parse_mode="Markdown"
    )

@bot.message_handler(content_types=["text"])
def handle_text(message):
    c = extract_coords_from_text(message.text)
    if not c:
        bot.reply_to(message, "⚠️ Koordinat alınamadı. `36.123456, 35.654321` gibi gönderin ya da fotoğraf yükleyin.")
        return
    lat, lon = c[0], c[1]
    bot.send_chat_action(message.chat.id, "upload_photo")
    img_bytes = generate_map_image(lat, lon)
    if not img_bytes:
        bot.reply_to(message, "⚠️ Harita alınamadı."); return
    address = reverse_geocode(lat, lon) if USE_ONLINE_REVERSE_GEOCODE else None
    if not address: address = get_address_simulation(lat, lon)
    caption = (f"Google Maps: https://www.google.com/maps?q={lat},{lon}\n"
               f"Apple Maps: https://maps.apple.com/?ll={lat},{lon}\n"
               f"Adres: {address}")

    # (Yeni) Yakın mekanlar
    if USE_NEARBY_POIS:
        pois = fetch_nearby_pois(lat, lon, radius=NEARBY_RADIUS, limit=NEARBY_LIMIT)
        if pois:
            caption += "\n\n📌 Yakındaki Mekanlar:\n" + "\n".join(pois)

    bot.send_photo(message.chat.id, img_bytes, caption=caption)

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_path = getattr(file_info, "file_path", None)
        if not file_path:
            bot.reply_to(message, "⚠️ Dosya bilgisi alınamadı.")
            return
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        r = requests.get(file_url, timeout=30); r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB")

        c = resolve_coords_from_any(img, caption_text=message.caption or "",
                                    file_name=os.path.basename(file_path) or "")
        if not c:
            bot.reply_to(message,
                         f"❔ Fotoğraftan koordinat çıkarılamadı.\n"
                         f"OCR: Paddle={PADDLE_AVAILABLE} / EasyOCR={EASYOCR_AVAILABLE} / Tesseract={TESS_AVAILABLE}\n"
                         "İpucu: Fotoğraf açıklamasına `36.12345 35.67890` yazabilirsin.")
            return

        lat, lon, source = c
        bot.send_chat_action(message.chat.id, "upload_photo")
        img_bytes = generate_map_image(lat, lon)
        if not img_bytes:
            bot.reply_to(message, "⚠️ Harita alınamadı."); return

        address = reverse_geocode(lat, lon) if USE_ONLINE_REVERSE_GEOCODE else None
        if not address: address = get_address_simulation(lat, lon)
        caption = (f"Kaynak: {source.upper()}\n"
                   f"Google Maps: https://www.google.com/maps?q={lat},{lon}\n"
                   f"Apple Maps: https://maps.apple.com/?ll={lat},{lon}\n"
                   f"Adres: {address}")

        # (Yeni) Yakın mekanlar
        if USE_NEARBY_POIS:
            pois = fetch_nearby_pois(lat, lon, radius=NEARBY_RADIUS, limit=NEARBY_LIMIT)
            if pois:
                caption += "\n\n📌 Yakındaki Mekanlar:\n" + "\n".join(pois)

        bot.send_photo(message.chat.id, img_bytes, caption=caption)
    except Exception as e:
        bot.reply_to(message, f"❌ Hata: {e}")

# ============= DAYANIKLI POLLING =============
if __name__ == "__main__":
    print("Bot çalışıyor...")

    backoff = 3  # saniye
    while True:
        try:
            bot.infinity_polling(
                timeout=20,
                long_polling_timeout=55,
                allowed_updates=["message", "callback_query"],
                skip_pending=True,
                logger_level=logging.INFO
            )
        except requests.exceptions.ConnectTimeout:
            log.warning("Connect timeout – yeniden dene...")
        except requests.exceptions.ReadTimeout:
            log.warning("Read timeout – yeniden dene...")
        except requests.exceptions.ConnectionError as e:
            log.warning(f"Bağlantı koptu: {e} – {backoff}s sonra tekrar...")
        except Exception as e:
            log.warning(f"Beklenmeyen hata: {e} – {backoff}s sonra tekrar...")

        time.sleep(backoff)
        backoff = min(backoff * 2, 60)
