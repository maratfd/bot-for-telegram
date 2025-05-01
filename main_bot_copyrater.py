import logging
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.enums import ParseMode
from datetime import datetime
import sqlite3
import requests
from typing import Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from aiogram.client.default import DefaultBotProperties

DEEPSEEK_URL = "https://www.deepseek.com/chat"

# ====== НАСТРОЙКИ ====== #
#BOT_TOKEN = ''
DEEPSEEK_API_KEY = "your_deepseek_api_key"
OPENAI_API_KEY = ''
DB_NAME = "bot_history.db"

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(
    #token='',
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Глобальные переменные
USER_SETTINGS: Dict[int, Dict[str, Any]] = {}  # {user_id: {"model": str, "temperature": float}}

# ====== БАЗА ДАННЫХ ====== #
def init_db():
    """Инициализация базы данных с настройками пользователей"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        # Таблица истории
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
        # Таблица настроек
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            model TEXT NOT NULL DEFAULT 'deepseek',
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
        
        # Настройки по умолчанию
        default_settings = {"model": "deepseek", "temperature": 0.7}
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
    """Основная клавиатура с учётом текущих настроек"""
    settings = get_user_settings(user_id)
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="DeepSeek" if settings["model"] != "deepseek" else "✅ DeepSeek"),
                KeyboardButton(text="OpenAI GPT" if settings["model"] != "openai" else "✅ OpenAI GPT")
            ],
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

# ====== ГЕНЕРАЦИЯ ТЕКСТА ====== #
async def generate_text(user_id: int, prompt: str) -> str:
    """Генерация текста с учётом настроек пользователя"""
    settings = get_user_settings(user_id)
    
    if settings["model"] == "deepseek":
        return await generate_with_api(
            url=DEEPSEEK_URL,
            api_key=DEEPSEEK_API_KEY,
            model="deepseek-chat",
            prompt=prompt,
            temperature=settings["temperature"]
        )
    else:
        return await generate_with_api(
            url="https://api.openai.com/v1/chat/completions",
            api_key=OPENAI_API_KEY,
            model="gpt-3.5-turbo",
            prompt=prompt,
            temperature=settings["temperature"]
        )

async def generate_with_api(url: str, api_key: str, model: str, prompt: str, temperature: float) -> str:
    """Общая функция для генерации через API"""
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"API Error ({model}): {e}")
        return None

# ====== ОБРАБОТЧИКИ ====== #
@dp.message(Command("start"))
async def cmd_start(message: Message):
    settings = get_user_settings(message.from_user.id)
    await message.answer(
        f"✨ <b>AI-копирайтер</b> готов к работе!\n\n"
        f"Текущие настройки:\n"
        f"• Модель: <b>{settings['model'].upper()}</b>\n"
        f"• Креативность: <b>{settings['temperature']}</b>\n\n"
        "Используй кнопки для управления или просто отправь запрос.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "🛠 Настройки")
async def show_settings(message: Message):
    settings = get_user_settings(message.from_user.id)
    await message.answer(
        f"⚙️ <b>Текущие настройки:</b>\n"
        f"• Модель: <b>{settings['model'].upper()}</b>\n"
        f"• Креативность: <b>{settings['temperature']}</b>\n\n"
        "Выбери действие:",
        reply_markup=get_settings_keyboard()
    )

@dp.message(F.text.startswith("🎨 Креативность:"))
async def show_creativity_info(message: Message):
    settings = get_user_settings(message.from_user.id)
    await message.answer(
        f"🎨 <b>Уровень креативности:</b> {settings['temperature']}\n\n"
        "0.0 - строгий и точный\n"
        "0.5 - баланс креативности и точности\n"
        "1.0 - максимально креативный\n\n"
        "Изменить можно в настройках (/settings)"
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
    update_user_setting(user_id, "model", "deepseek")
    update_user_setting(user_id, "temperature", 0.7)
    await callback.message.edit_text(
        "⚙️ <b>Настройки сброшены к значениям по умолчанию:</b>\n"
        "• Модель: DEEPSEEK\n"
        "• Креативность: 0.7",
        reply_markup=get_settings_keyboard()
    )
    await callback.answer()

@dp.message(F.text.in_(["DeepSeek", "OpenAI GPT"]))
async def change_model(message: Message):
    user_id = message.from_user.id
    new_model = "deepseek" if message.text == "DeepSeek" else "openai"
    update_user_setting(user_id, "model", new_model)
    await message.answer(
        f"✅ Модель изменена на <b>{new_model.upper()}</b>",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message(F.text == "📜 История")
async def show_history(message: Message):
    history = get_user_history(message.from_user.id)
    if not history:
        await message.answer("📭 История запросов пуста")
        return
    
    text = "📜 <b>Последние запросы:</b>\n\n"
    for i, (timestamp, model, temp, prompt, _) in enumerate(history, 1):
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
    if message.text in ["DeepSeek", "OpenAI GPT", "🎨 Креативность:", "📜 История", "🛠 Настройки"]:
        return
    
    user_id = message.from_user.id
    await message.answer("🔄 <i>Генерирую текст...</i>")
    
    generated_text = await generate_text(user_id, message.text)
    if not generated_text:
        await message.answer("❌ Ошибка генерации. Попробуйте позже.")
        return
    
    settings = get_user_settings(user_id)
    add_to_history(
        user_id=user_id,
        model=settings["model"],
        temperature=settings["temperature"],
        prompt=message.text,
        response=generated_text
    )
    
    await message.answer(
        f"📝 <b>Результат ({settings['model'].upper()}, креативность {settings['temperature']}):</b>\n\n"
        f"{generated_text}",
        reply_markup=get_main_keyboard(user_id)
    )

# ====== ЗАПУСК ====== #
if __name__ == "__main__":
    init_db()
    logger.info("Бот запущен! База данных инициализирована.")
    dp.run_polling(bot)
