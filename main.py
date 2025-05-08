import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart
import logging
from dotenv import load_dotenv
import os

import json
from datetime import datetime, timedelta

load_dotenv('.env')

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
INVITE_LINKS = os.getenv("INVITE_LINKS").split(",")


logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Словарь для хранения хэшей пользователей временно
pending_hashes = {}

USED_LINKS_FILE = "used_links.txt"

def load_used_links():
    if not os.path.exists(USED_LINKS_FILE):
        return set()
    with open(USED_LINKS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_used_link(link):
    with open(USED_LINKS_FILE, "a") as f:
        f.write(link + "\n")

def get_fresh_invite_link():
    used = load_used_links()
    for link in INVITE_LINKS:
        if link not in used:
            save_used_link(link)
            return link
    return None

SUBSCRIPTIONS_FILE = "subscriptions.json"

def load_subscriptions():
    if not os.path.exists(SUBSCRIPTIONS_FILE):
        return {}
    with open(SUBSCRIPTIONS_FILE, "r") as f:
        return json.load(f)

def save_subscriptions(subs):
    with open(SUBSCRIPTIONS_FILE, "w") as f:
        json.dump(subs, f, indent=4)


def add_subscription(username: str, user_id: int, duration_days: int, price: int):
    subs = load_subscriptions()
    end_date = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d")

    subs[username] = {
        "id": user_id,
        "duration_days": duration_days,
        "price": price,
        "end_date": end_date
    }
    save_subscriptions(subs)

def get_subscription_info(username):
    subs = load_subscriptions()
    entry = subs.get(username)
    if not entry:
        return None

    end_date = datetime.strptime(entry["end_date"], "%Y-%m-%d")
    remaining_days = (end_date - datetime.now()).days

    if remaining_days < 0:
        return None

    return {
        "days_total": entry["duration_days"],
        "days_left": remaining_days,
        "end_date": entry["end_date"]
    }

@dp.message(CommandStart())
async def start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Подписки", callback_data="subs")],
        [InlineKeyboardButton(text="💸 Тарифы", callback_data="plans")]
    ])
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=kb)

@dp.callback_query(F.data == "subs")
async def show_subscriptions(callback: types.CallbackQuery):
    info = get_subscription_info(callback.from_user.username)
    if info:
        await callback.message.answer(
            f"Ваши подписки:\n"
            f"Подписка на {info['days_total']} дней.\n"
            f"Подписка истечет через {info['days_left']} дней."
        )
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Перейти к тарифам", callback_data="plans")]
        ])
        await callback.message.answer("У вас нет активных подписок.", reply_markup=kb)

@dp.callback_query(F.data == "plans")
async def show_plans(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="2 недели - 30", callback_data="plan_2")],
        [InlineKeyboardButton(text="1 месяц - 50$", callback_data="plan_1")],
        [InlineKeyboardButton(text="3 месяца - 100$", callback_data="plan_3")]
    ])
    await callback.message.edit_text("Выберите желаемый тарифный план:", reply_markup=kb)

@dp.callback_query(F.data.in_(["plan_1", "plan_2", "plan_3"]))
async def choose_plan(callback: types.CallbackQuery):
    if callback.data == "plan_2":
        duration = "14 дней"
    elif callback.data == "plan_1":
        duration = "30 дней"
    else:
        duration = "90 дней"
    if callback.data == "plan_2":
        price = '30$'
    elif callback.data == 'plan_1':
        price = '50$'
    else:
        price = '100$'
    plan_id = callback.data

    payment_text = (
        f"<b>{duration}</b>\nЦена: {price}\n\n"
        "Реквизиты:\n\n"
        "<b>USDT/ETH (ERC20/BEP20)</b>\n"
        "<code>0x5b14bf001d58a8b4fae027fb670874e43bf6030e</code>\n\n"
        "<b>USDT (TRC20)</b>\n"
        "<code>TURQhUFCVx4Z3aDpKgpA1NB1moGB3maRbn</code>\n\n"
        "<b>SOL</b>\n"
        "<code>2pZq9xPShNmuqt9QoaJiw5hAkD1LU5pue6bkmbnActue</code>\n\n"
        "Сохраните хэш транзакции для дальнейшего подтверждения."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{plan_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="plans")]
    ])

    await callback.message.edit_text(
        payment_text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


@dp.callback_query(F.data.startswith("paid_"))
async def wait_for_hash(callback: types.CallbackQuery):
    await callback.message.answer("Отправьте ваш хэш транзакции для проверки")
    pending_hashes[callback.from_user.id] = {
        "plan": callback.data,
        "username": callback.from_user.username or callback.from_user.id
    }

@dp.message()
async def receive_tx_hash(message: types.Message):
    user_id = message.from_user.id
    if user_id not in pending_hashes:
        await message.answer("Неожиданное сообщение. Начните с /start")
        return

    tx_hash = message.text.strip()
    plan_data = pending_hashes.pop(user_id)
    plan = plan_data["plan"]
    username = plan_data["username"]

    if plan == "paid_plan_2":
        duration = 14
        price = 30
    elif plan == "paid_plan_1":
        duration = 30
        price = 50
    elif plan == "paid_plan_3":
        duration = 90
        price = 100
    else:
        await message.answer("Ошибка данных плана.")
        return

    add_subscription(username, user_id, duration, price)

    admin_text = (
        f"Новая оплата!\n"
        f"Пользователь: @{username}\n"
        f"Тип подписки: {duration} дней\n"
        f"Цена: {price}$\n"
        f"Хэш: {tx_hash}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выдать ссылку", callback_data=f"approve_{user_id}")],
        [InlineKeyboardButton(text="Ошибка", callback_data=f"reject_{user_id}")]
    ])
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb)

    await message.answer("Отлично! Ваша транзакция проверяется. Обычно проверка занимает не более суток.")

@dp.callback_query(F.data.startswith("approve_"))
async def send_link(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    invite_link = get_fresh_invite_link()

    if invite_link:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 Подписки", callback_data="subs")]
        ])
        await bot.send_message(
            user_id,
            f"Спасибо за оформление подписки! Твоя ссылка: {invite_link}\nРады видеть тебя в нашем комьюнити!",
            reply_markup=kb
        )
        await callback.message.delete()
        await callback.answer("Ссылка отправлена.")
    else:
        await bot.send_message(
            user_id,
            "Извините, сейчас нет доступных ссылок. Свяжитесь с админом."
        )
        await callback.message.delete()
        await callback.answer("Ссылки закончились.")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="plans")]
    ])
    await bot.send_message(user_id,
                           "Произошла ошибка при проверке транзакции. Попробуйте позже.",
                           reply_markup=kb
                           )
    await callback.message.delete()
    await callback.answer("Пользователю отправлено сообщение об ошибке.")

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
