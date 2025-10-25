import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("👋 Merhaba! Bana koordinat gönder (örn: 41.0082, 28.9784) ve ben sana Google Maps linki vereyim.")

@dp.message()
async def coords_to_maps(message: types.Message):
    text = message.text.replace(',', ' ').strip()
    parts = text.split()

    try:
        lat = float(parts[0])
        lon = float(parts[1])
        link = f"https://www.google.com/maps?q={lat},{lon}"
        await message.reply(f"📍 {link}")
    except:
        pass  # koordinat değilse sessiz geç

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
