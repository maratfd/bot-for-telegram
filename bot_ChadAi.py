
import logging
import aiohttp
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from typing import Dict, Any

# ====== НАСТРОЙКИ ====== #
BOT_TOKEN = ''
CHAD_API_KEY = ''
CHAD_API_URL = 'https://ask.chadgpt.ru/api/public/gpt-4o-mini'
DB_NAME = "bot_history.db"
REQUEST_TIMEOUT = 25  # Секунд

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ БОТА И ДИСПЕТЧЕРА ====== #
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ====== БАЗА ДАННЫХ ====== #
def init_db():
    """Инициализация базы данных"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            model TEXT NOT NULL,
            temperature REAL NOT NULL,
            prompt TEXT NOT NULL,
            response TEXT NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL DEFAULT 'chadai',
            temperature REAL NOT NULL DEFAULT 0.7
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON history (user_id)")
        conn.commit()

def get_user_settings(user_id: int) -> Dict[str, Any]:
    """Получение настроек пользователя"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT model, temperature FROM user_settings WHERE user_id = ?", (user_id,))
        settings = cursor.fetchone()
        
        if settings:
            return {"model": settings[0], "temperature": settings[1]}
        
        default_settings = {"model": "chadai", "temperature": 0.7}
        cursor.execute(
            "INSERT INTO user_settings (user_id, model, temperature) VALUES (?, ?, ?)",
            (user_id, default_settings["model"], default_settings["temperature"])
        )
        conn.commit()
        return default_settings

def update_user_setting(user_id: int, key: str, value: Any):
    """Обновление настроек пользователя"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE user_settings SET {key} = ? WHERE user_id = ?",
            (value, user_id)
        )
        conn.commit()

def add_to_history(user_id: int, model: str, temperature: float, prompt: str, response: str):
    """Добавление записи в историю"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO history (user_id, model, temperature, prompt, response)
        VALUES (?, ?, ?, ?, ?)
        """, (user_id, model, temperature, prompt, response))
        conn.commit()

def get_user_history(user_id: int, limit: int = 5):
    """Получение истории пользователя"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT timestamp, model, temperature, prompt, response 
        FROM history 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
        """, (user_id, limit))
        return cursor.fetchall()

def clear_user_history(user_id: int):
    """Очистка истории пользователя"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount

# ====== КЛАВИАТУРЫ ====== #
def get_main_keyboard(user_id: int):
    """Основная клавиатура"""
    settings = get_user_settings(user_id)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="ChadAI" if settings["model"] != "chadai" else "✅ ChadAI")],
            [
                KeyboardButton(text=f"🎨 Креативность: {settings['temperature']}"),
                KeyboardButton(text="📜 История")
            ],
            [KeyboardButton(text="🛠 Настройки")]
        ],
        resize_keyboard=True
    )

def get_settings_keyboard():
    """Клавиатура для настроек"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬆️ Увеличить креативность", callback_data="increase_temp"),
                InlineKeyboardButton(text="⬇️ Уменьшить креативность", callback_data="decrease_temp")
            ],
            [
                InlineKeyboardButton(text="🔧 Сбросить настройки", callback_data="reset_settings"),
                InlineKeyboardButton(text="📜 Очистить историю", callback_data="clear_history")
            ]
        ]
    )

# ====== CHADGPT API ====== #
class ChadGPTAPI:
    def __init__(self):
        self.session = None
    
    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT))
    
    async def close(self):
        if self.session:
            await self.session.close()
    
    async def generate_response(self, prompt: str, temperature: float) -> str:
        try:
            await self.ensure_session()
            
            request_json = {
                "message": prompt,
                "api_key": CHAD_API_KEY
            }

            async with self.session.post(
                CHAD_API_URL,
                json=request_json
            ) as response:
                
                if response.status != 200:
                    logger.error(f"HTTP Error {response.status}")
                    return None
                
                data = await response.json()
                
                if data.get('is_success', False):
                    return data['response']
                else:
                    logger.error(f"API Error: {data.get('error_message', 'Unknown error')}")
                    return None
                    
        except Exception as e:
            logger.error(f"ChadGPT API Error: {str(e)}")
            return None

# Инициализация API
chad_api = ChadGPTAPI()

# ====== ОБРАБОТЧИКИ ====== #
@dp.message(Command("start"))
async def cmd_start(message: Message):
    settings = get_user_settings(message.from_user.id)
    await message.answer(
        "✨ <b>Чат-бот с ChadGPT</b> готов к работе!\n\n"
        f"Текущие настройки:\n"
        f"• Модель: <b>{settings['model'].upper()}</b>\n"
        f"• Креативность: <b>{settings['temperature']}</b>\n\n"
        "Отправьте мне сообщение, и я постараюсь на него ответить.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ <b>Справка по боту</b>\n\n"
        "Этот бот использует ChadGPT API для генерации ответов.\n\n"
        "Доступные команды:\n"
        "/start - начать работу\n"
        "/help - эта справка\n"
        "/status - проверить статус бота"
    )

@dp.message(Command("status"))
async def cmd_status(message: Message):
    await message.answer(
        "🟢 <b>Бот работает нормально</b>\n\n"
        "Последние действия:\n"
        f"• Пользователей в базе: {len(get_all_users())}\n"
        f"• Всего запросов: {get_total_requests()}"
    )

@dp.message(F.text == "🛠 Настройки")
async def show_settings(message: Message):
    settings = get_user_settings(message.from_user.id)
    await message.answer(
        f"⚙️ <b>Текущие настройки:</b>\n"
        f"• Модель: <b>{settings['model'].upper()}</b>\n"
        f"• Креативность: <b>{settings['temperature']}</b>\n\n"
        "Выберите действие:",
        reply_markup=get_settings_keyboard()
    )

@dp.callback_query(F.data == "increase_temp")
async def increase_temperature(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    new_temp = min(1.0, round(settings["temperature"] + 0.1, 1))
    update_user_setting(user_id, "temperature", new_temp)
    await callback.message.edit_text(
        f"⚙️ <b>Креативность увеличена до:</b> {new_temp}",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "decrease_temp")
async def decrease_temperature(callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = get_user_settings(user_id)
    new_temp = max(0.0, round(settings["temperature"] - 0.1, 1))
    update_user_setting(user_id, "temperature", new_temp)
    await callback.message.edit_text(
        f"⚙️ <b>Креативность уменьшена до:</b> {new_temp}",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "reset_settings")
async def reset_settings(callback: CallbackQuery):
    user_id = callback.from_user.id
    update_user_setting(user_id, "model", "chadai")
    update_user_setting(user_id, "temperature", 0.7)
    await callback.message.edit_text(
        "⚙️ <b>Настройки сброшены к значениям по умолчанию:</b>\n"
        "• Модель: CHADAI\n"
        "• Креативность: 0.7",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.message(F.text == "📜 История")
async def show_history(message: Message):
    history = get_user_history(message.from_user.id)
    if not history:
        await message.answer("📭 История запросов пуста")
        return
    
    text = "📜 <b>Последние запросы:</b>\n\n"
    for i, (timestamp, model, temp, prompt, response) in enumerate(history, 1):
        text += (
            f"{i}. <i>{timestamp}</i>\n"
            f"• Модель: <b>{model.upper()}</b>\n"
            f"• Креативность: <b>{temp}</b>\n"
            f"• Запрос: <i>{prompt[:50]}{'...' if len(prompt) > 50 else ''}</i>\n\n"
        )
    
    await message.answer(text)

@dp.callback_query(F.data == "clear_history")
async def clear_history_handler(callback: CallbackQuery):
    deleted_count = clear_user_history(callback.from_user.id)
    await callback.message.answer(
        f"✅ Удалено {deleted_count} записей из истории" if deleted_count > 0 
        else "📭 История уже пуста"
    )
    await callback.answer()

@dp.message(F.text)
async def handle_text(message: Message):
    if message.text in ["ChadAI", "🎨 Креативность:", "📜 История", "🛠 Настройки"]:
        return
    
    user_id = message.from_user.id
    processing_msg = await message.answer("🔄 Обрабатываю запрос...")
    
    try:
        settings = get_user_settings(user_id)
        response = await chad_api.generate_response(message.text, settings["temperature"])
        
        if response:
            add_to_history(
                user_id=user_id,
                model=settings["model"],
                temperature=settings["temperature"],
                prompt=message.text,
                response=response
            )
            #used_words = response_data.get('used_words_count', 'N/A')
            await processing_msg.edit_text(
                f"📝 <b>Результат (креативность {settings['temperature']}):</b>\n\n{response}"
                #f"📊 Использовано слов: {used_words}"
            )
        else:
            await processing_msg.edit_text(
                "❌ Не удалось получить ответ от сервиса.\n"
                "Попробуйте:\n"
                "1. Изменить запрос\n"
                "2. Уменьшить креативность\n"
                "3. Повторить позже"
            )
            
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}", exc_info=True)
        await message.answer("⚠️ Произошла критическая ошибка. Администратор уведомлен.")

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====== #
def get_all_users():
    """Получить список всех пользователей"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_id FROM user_settings")
        return cursor.fetchall()

def get_total_requests():
    """Получить общее количество запросов"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM history")
        return cursor.fetchone()[0]

# ====== ЗАПУСК И ЗАВЕРШЕНИЕ ====== #
async def on_startup():
    """Действия при запуске"""
    init_db()
    logger.info("Database initialized")
    logger.info("Starting bot...")

async def on_shutdown():
    """Действия при завершении"""
    await chad_api.close()
    logger.info("Bot shutdown complete")

async def main():
    """Основная функция"""
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
