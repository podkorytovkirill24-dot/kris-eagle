from aiogram import Bot

from config import config
from keyboards.admin import request_decision_keyboard


def _format_admin_request_text(request_row: dict) -> str:
    username = request_row.get("username")
    username_line = f"username: @{username}" if username else "username: отсутствует"
    price_text = f"{float(request_row.get('selected_price_usdt', 0)):g}"
    return (
        "🔥 Новая оплаченная заявка\n\n"
        f"ID заявки: {request_row['id']}\n"
        f"user_id: {request_row['user_id']}\n"
        f"{username_line}\n"
        f"Услуга: {request_row['service_title']}\n"
        f"Тариф: {int(request_row.get('selected_days') or 0)} дн. / {price_text} USDT\n"
        f"Текст:\n{request_row['text_content']}"
    )


async def notify_admins_about_request(bot: Bot, request_row: dict) -> None:
    text = _format_admin_request_text(request_row)
    kb = request_decision_keyboard(request_row["id"])
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception:
            continue
