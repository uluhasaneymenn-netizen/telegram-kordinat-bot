from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = "8432197907:AAFWPgEDYeqe-hFVFXdCA8U7i0aB20VN7OQ"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler()
async def coords_to_maps(message: types.Message):
    text = message.text.replace(',', ' ').strip()
    parts = text.split()

    try:
        lat = float(parts[0])
        lon = float(parts[1])
        link = f"https://www.google.com/maps?q={lat},{lon}"
        await message.reply(f"📍 {link}")
    except:
        pass  # koordinat değilse cevap verme

if __name__ == '__main__':
    executor.start_polling(dp)
