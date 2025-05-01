import os
import logging
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Загрузка конфигурации
#load_dotenv()
#BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 521188043

# Инициализация бота и диспетчера
bot = Bot(token='7125055805:AAGm9c3MUZGsVXLV5Dgmxt914hTJ47bz1Lg')
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния FSM
class ProductState(StatesGroup):
    name = State()
    description = State()
    price = State()
    photo = State()

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@router.message(Command("start"))
async def start_handler(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🛍️ Каталог", callback_data="show_catalog"),
        InlineKeyboardButton(text="🛒 Корзина", callback_data="show_cart")
    )
    await message.answer(
        "👋 Добро пожаловать в магазин! Выберите действие:",
        reply_markup=builder.as_markup()
    )

# ========== ОБРАБОТЧИКИ CALLBACK ==========
@router.callback_query(F("show_catalog"))
async def show_catalog(callback: types.CallbackQuery):
    # Здесь должна быть логика загрузки товаров из БД
    products = [
        {"id": 1, "name": "Товар 1", "price": 1000},
        {"id": 2, "name": "Товар 2", "price": 2000}
    ]
    
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.button(
            text=f"{product['name']} - {product['price']}₽",
            callback_data=f"product_{product['id']}"
        )
    builder.adjust(1)
    
    await callback.message.edit_text(
        "📦 Каталог товаров:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F(startswith="product_"))
async def show_product(callback: types.CallbackQuery):
    product_id = callback.data.split("_")[1]
    # Здесь должна быть логика загрузки товара из БД
    product = {
        "name": f"Товар {product_id}",
        "description": "Отличный товар!",
        "price": 1000,
        "photo": None  # Можно добавить file_id фото
    }
    
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить в корзину", callback_data=f"add_{product_id}")
    builder.button(text="🔙 Назад", callback_data="show_catalog")
    builder.adjust(1)
    
    if product['photo']:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=product['photo'],
            caption=f"<b>{product['name']}</b>\n\n{product['description']}\n\n💰 Цена: <b>{product['price']}₽</b>",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            f"<b>{product['name']}</b>\n\n{product['description']}\n\n💰 Цена: <b>{product['price']}₽</b>",
            reply_markup=builder.as_markup()
        )
    await callback.answer()

# ========== АДМИН ПАНЕЛЬ ==========
@router.message(Command("add_product"), lambda message: message.from_user.id == ADMIN_ID)
async def add_product_start(message: types.Message, state: FSMContext):
    await state.set_state(ProductState.name)
    await message.answer("📝 Введите название товара:")

@router.message(ProductState.name)
async def set_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ProductState.description)
    await message.answer("📝 Введите описание товара:")

# ========== ЗАПУСК БОТА ==========
async def main():
    logger.info("Starting bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
