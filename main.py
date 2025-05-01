import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
import logging

from database import Database

# Загрузка конфигов
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db = Database("database.db")

# Состояния FSM
class ProductState(StatesGroup):
    name = State()
    description = State()
    price = State()
    photo = State()

# Команда /start
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    if not db.user_exists(user_id):
        db.add_user(user_id)
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🛍️ Каталог", callback_data="catalog"))
    keyboard.add(InlineKeyboardButton("🛒 Корзина", callback_data="cart"))
    
    await message.answer(
        "👋 Добро пожаловать в магазин! Выберите действие:",
        reply_markup=keyboard
    )

# Показать каталог
@dp.callback_query_handler(lambda c: c.data == 'catalog')
async def show_catalog(callback: types.CallbackQuery):
    products = db.get_products()
    keyboard = InlineKeyboardMarkup()
    
    for product in products:
        keyboard.add(
            InlineKeyboardButton(
                f"{product[1]} - {product[3]}₽",
                callback_data=f"product_{product[0]}"
            )
        )
    
    await bot.send_message(
        callback.from_user.id,
        "📦 **Каталог товаров**:",
        reply_markup=keyboard
    )

# Показать товар
@dp.callback_query_handler(lambda c: c.data.startswith('product_'))
async def show_product(callback: types.CallbackQuery):
    product_id = int(callback.data.split('_')[1])
    product = db.get_product(product_id)
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("➕ Добавить в корзину", callback_data=f"add_to_cart_{product_id}"))
    
    await bot.send_photo(
        callback.from_user.id,
        photo=product[4],  # Фото товара
        caption=f"**{product[1]}**\n\n{product[2]}\n\n💰 Цена: **{product[3]}₽**",
        reply_markup=keyboard
    )

# Добавить в корзину
@dp.callback_query_handler(lambda c: c.data.startswith('add_to_cart_'))
async def add_to_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    product_id = int(callback.data.split('_')[3])
    db.add_to_cart(user_id, product_id)
    await callback.answer("✅ Товар добавлен в корзину!")

# Показать корзину
@dp.callback_query_handler(lambda c: c.data == 'cart')
async def show_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cart_items = db.get_cart(user_id)
    total = sum(item[3] for item in cart_items)  # Сумма товаров
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("💳 Оформить заказ", callback_data="checkout"))
    
    items_text = "\n".join([f"➡️ {item[1]} - {item[3]}₽" for item in cart_items])
    await bot.send_message(
        callback.from_user.id,
        f"🛒 **Ваша корзина**:\n\n{items_text}\n\n💸 **Итого: {total}₽**",
        reply_markup=keyboard
    )

# Оформление заказа (через Telegram Payments)
@dp.callback_query_handler(lambda c: c.data == 'checkout')
async def checkout(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cart_items = db.get_cart(user_id)
    total = sum(item[3] for item in cart_items) * 100  # В копейках
    
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Оплата заказа",
        description="Оплатите ваш заказ",
        payload="order_payload",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="Общая сумма", amount=total)],
        start_parameter="test"
    )

# Админ-панель (добавление товара)
@dp.message_handler(commands=['add_product'], user_id=ADMIN_ID)
async def add_product_start(message: types.Message):
    await ProductState.name.set()
    await message.answer("📝 Введите название товара:")

@dp.message_handler(state=ProductState.name)
async def set_product_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['name'] = message.text
    await ProductState.next()
    await message.answer("📝 Введите описание товара:")

@dp.message_handler(state=ProductState.description)
async def set_product_description(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['description'] = message.text
    await ProductState.next()
    await message.answer("💰 Введите цену товара (в рублях):")

@dp.message_handler(state=ProductState.price)
async def set_product_price(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['price'] = int(message.text)
    await ProductState.next()
    await message.answer("📸 Пришлите фото товара:")

@dp.message_handler(content_types=['photo'], state=ProductState.photo)
async def set_product_photo(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['photo'] = message.photo[-1].file_id
        db.add_product(data['name'], data['description'], data['price'], data['photo'])
    
    await state.finish()
    await message.answer("✅ Товар успешно добавлен!")

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)

