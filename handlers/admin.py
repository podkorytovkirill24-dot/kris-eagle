from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import config
from database import db
from keyboards.admin import (
    admin_broadcast_item_keyboard,
    admin_broadcast_menu_keyboard,
    back_keyboard,
    admin_main_keyboard,
    admin_plan_item_keyboard,
    admin_plans_keyboard,
    admin_service_actions_keyboard,
    admin_services_list_keyboard,
    request_decision_keyboard,
)

router = Router()


class AdminFilter(BaseFilter):
    async def __call__(self, message: Message | CallbackQuery) -> bool:
        user = message.from_user
        return bool(user and user.id in config.admin_ids)


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


class AdminStates(StatesGroup):
    plan_add_days = State()
    plan_add_price = State()
    bc_chat = State()
    bc_thread = State()
    bc_interval = State()
    bc_text = State()


def _fmt_price(price: float) -> str:
    return f"{price:g}"


def _fmt_iso(iso_value: str | None) -> str:
    if not iso_value:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_value)
        return dt.strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso_value


@router.callback_query(F.data == "admin:main")
async def admin_main(call: CallbackQuery) -> None:
    await call.message.edit_text("⚙️ Админ-панель", reply_markup=admin_main_keyboard())
    await call.answer()


@router.callback_query(F.data == "admin:services")
async def admin_services(call: CallbackQuery) -> None:
    services = await db.get_all_services()
    if not services:
        await call.message.edit_text("Услуги не найдены.", reply_markup=admin_main_keyboard())
        await call.answer()
        return
    await call.message.edit_text(
        "🛠 Выберите услугу для управления:",
        reply_markup=admin_services_list_keyboard([dict(item) for item in services]),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_svc:open:"))
async def admin_service_open_inline(call: CallbackQuery) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service:
        await call.answer("Услуга не найдена.", show_alert=True)
        return

    plans = await db.get_service_plans(service_id)
    plans_count = len(plans)
    active_count = len([p for p in plans if int(p["is_enabled"]) == 1])
    status = "🟢 Включена" if int(service["is_enabled"]) else "🔴 Отключена"

    await call.message.edit_text(
        f"Услуга: {service['title']}\n"
        f"Статус: {status}\n"
        f"Тарифов: {plans_count} (активных: {active_count})",
        reply_markup=admin_service_actions_keyboard(service_id, int(service["is_enabled"])),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_svc:toggle:"))
async def admin_toggle_service(call: CallbackQuery) -> None:
    service_id = int(call.data.split(":")[2])
    await db.toggle_service(service_id)
    service = await db.get_service(service_id)
    if not service:
        await call.answer()
        return

    plans = await db.get_service_plans(service_id)
    plans_count = len(plans)
    active_count = len([p for p in plans if int(p["is_enabled"]) == 1])
    status = "🟢 Включена" if int(service["is_enabled"]) else "🔴 Отключена"

    await call.message.edit_text(
        f"Услуга: {service['title']}\n"
        f"Статус: {status}\n"
        f"Тарифов: {plans_count} (активных: {active_count})",
        reply_markup=admin_service_actions_keyboard(service_id, int(service["is_enabled"])),
    )
    await call.answer("Статус услуги изменен.")


@router.callback_query(F.data.startswith("adm_plan:list:"))
async def admin_plan_list(call: CallbackQuery) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service:
        await call.answer("Услуга не найдена.", show_alert=True)
        return

    plans = await db.get_service_plans(service_id, only_enabled=False)
    lines = [f"💳 Тарифы для: {service['title']}"]
    if not plans:
        lines.append("Тарифов пока нет.")
    else:
        for p in plans:
            mark = "🟢" if int(p["is_enabled"]) else "🔴"
            lines.append(f"{mark} {int(p['days'])} дн. — {_fmt_price(float(p['price_usdt']))} USDT")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_plans_keyboard(service_id, [dict(p) for p in plans]),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_plan:open:"))
async def admin_plan_open(call: CallbackQuery) -> None:
    _, _, _, plan_id_s, service_id_s = call.data.split(":")
    plan_id = int(plan_id_s)
    service_id = int(service_id_s)
    plan = await db.get_service_plan(plan_id)
    if not plan:
        await call.answer("Тариф не найден.", show_alert=True)
        return

    text = (
        f"Тариф #{plan['id']}\n"
        f"Срок: {int(plan['days'])} дн.\n"
        f"Цена: {_fmt_price(float(plan['price_usdt']))} USDT\n"
        f"Статус: {'Включен' if int(plan['is_enabled']) else 'Выключен'}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_plan_item_keyboard(plan_id, service_id, int(plan["is_enabled"])),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm_plan:add:"))
async def admin_plan_add_start(call: CallbackQuery, state: FSMContext) -> None:
    service_id = int(call.data.split(":")[2])
    await state.set_state(AdminStates.plan_add_days)
    await state.update_data(service_id=service_id)
    await call.message.answer(
        "Введите срок тарифа в днях (целое число):",
        reply_markup=back_keyboard(f"adm_plan:cancel_add:{service_id}", "⬅️ К тарифам"),
    )
    await call.answer()


@router.message(AdminStates.plan_add_days)
async def admin_plan_add_days(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    service_id = int(data["service_id"])
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(
            "Нужно положительное целое число дней.",
            reply_markup=back_keyboard(f"adm_plan:cancel_add:{service_id}", "⬅️ К тарифам"),
        )
        return
    await state.update_data(days=int(raw))
    await state.set_state(AdminStates.plan_add_price)
    await message.answer(
        "Введите цену в USDT (например 1.5):",
        reply_markup=back_keyboard(f"adm_plan:cancel_add:{service_id}", "⬅️ К тарифам"),
    )


@router.message(AdminStates.plan_add_price)
async def admin_plan_add_price(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    service_id = int(data["service_id"])
    raw = (message.text or "").strip().replace(",", ".")
    try:
        price = float(raw)
    except ValueError:
        await message.answer(
            "Цена должна быть числом.",
            reply_markup=back_keyboard(f"adm_plan:cancel_add:{service_id}", "⬅️ К тарифам"),
        )
        return
    if price <= 0:
        await message.answer(
            "Цена должна быть больше 0.",
            reply_markup=back_keyboard(f"adm_plan:cancel_add:{service_id}", "⬅️ К тарифам"),
        )
        return

    days = int(data["days"])
    plan_id = await db.upsert_service_plan(service_id=service_id, days=days, price_usdt=price)
    await state.clear()
    await message.answer(f"Тариф сохранен. ID: {plan_id} ({days} дн. / {_fmt_price(price)} USDT)")


@router.callback_query(F.data.startswith("adm_plan:toggle:"))
async def admin_plan_toggle(call: CallbackQuery) -> None:
    _, _, _, plan_id_s, service_id_s = call.data.split(":")
    plan_id = int(plan_id_s)
    service_id = int(service_id_s)
    await db.toggle_service_plan(plan_id)
    plan = await db.get_service_plan(plan_id)
    if not plan:
        await call.answer("Тариф не найден.", show_alert=True)
        return

    await call.message.edit_text(
        f"Тариф #{plan['id']}\n"
        f"Срок: {int(plan['days'])} дн.\n"
        f"Цена: {_fmt_price(float(plan['price_usdt']))} USDT\n"
        f"Статус: {'Включен' if int(plan['is_enabled']) else 'Выключен'}",
        reply_markup=admin_plan_item_keyboard(plan_id, service_id, int(plan["is_enabled"])),
    )
    await call.answer("Статус тарифа изменен.")


@router.callback_query(F.data.startswith("adm_plan:delete:"))
async def admin_plan_delete(call: CallbackQuery) -> None:
    _, _, _, plan_id_s, service_id_s = call.data.split(":")
    plan_id = int(plan_id_s)
    service_id = int(service_id_s)
    await db.delete_service_plan(plan_id)
    service = await db.get_service(service_id)
    plans = await db.get_service_plans(service_id, only_enabled=False)
    lines = [f"💳 Тарифы для: {service['title'] if service else service_id}"]
    if not plans:
        lines.append("Тарифов пока нет.")
    else:
        for p in plans:
            mark = "🟢" if int(p["is_enabled"]) else "🔴"
            lines.append(f"{mark} {int(p['days'])} дн. — {_fmt_price(float(p['price_usdt']))} USDT")
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_plans_keyboard(service_id, [dict(p) for p in plans]),
    )
    await call.answer("Тариф удален.")


@router.callback_query(F.data.startswith("adm_plan:cancel_add:"))
async def admin_plan_cancel_add(call: CallbackQuery, state: FSMContext) -> None:
    service_id = int(call.data.split(":")[3])
    await state.clear()
    service = await db.get_service(service_id)
    plans = await db.get_service_plans(service_id, only_enabled=False)
    lines = [f"💳 Тарифы для: {service['title'] if service else service_id}"]
    if not plans:
        lines.append("Тарифов пока нет.")
    else:
        for p in plans:
            mark = "🟢" if int(p["is_enabled"]) else "🔴"
            lines.append(f"{mark} {int(p['days'])} дн. — {_fmt_price(float(p['price_usdt']))} USDT")
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=admin_plans_keyboard(service_id, [dict(p) for p in plans]),
    )
    await call.answer()


@router.callback_query(F.data == "admin:requests")
async def admin_requests(call: CallbackQuery) -> None:
    items = await db.get_pending_requests()
    if not items:
        await call.message.answer("Нет заявок на проверку.")
        await call.answer()
        return
    for row in items[:20]:
        username = row["username"] or "без username"
        text = (
            f"📥 Заявка #{row['id']}\n"
            f"user_id: {row['user_id']}\n"
            f"username: @{username}\n"
            f"Услуга: {row['service_title']}\n"
            f"Тариф: {int(row['selected_days'] or 0)} дн. / {_fmt_price(float(row['selected_price_usdt'] or 0))} USDT\n"
            f"Создана: {_fmt_iso(row['created_at'])}\n"
            f"Текст:\n{row['text_content']}"
        )
        await call.message.answer(text, reply_markup=request_decision_keyboard(int(row["id"])))
    await call.answer()


@router.callback_query(F.data.startswith("adm_req:"))
async def admin_request_decision(call: CallbackQuery) -> None:
    _, decision, req_id_s = call.data.split(":")
    req_id = int(req_id_s)
    req = await db.get_request(req_id)
    if not req:
        await call.answer("Заявка не найдена.", show_alert=True)
        return

    if decision == "approve":
        updated = await db.approve_request(req_id)
        if updated:
            user_text = (
                f"✅ Ваша заявка #{req_id} одобрена.\n"
                f"Услуга: {updated['service_title']}\n"
                f"Срок: {int(updated['selected_days'])} дн.\n"
                f"Действует до: {_fmt_iso(updated['expires_at'])}"
            )
        else:
            user_text = f"✅ Ваша заявка #{req_id} одобрена."
        admin_text = f"Заявка #{req_id} одобрена."
    else:
        await db.update_request_status(req_id, "rejected")
        user_text = f"❌ Ваша заявка #{req_id} отклонена."
        admin_text = f"Заявка #{req_id} отклонена."

    try:
        await call.bot.send_message(int(req["user_id"]), user_text)
    except Exception:
        pass

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(admin_text)
    await call.answer()


@router.callback_query(F.data == "admin:logs")
async def admin_logs(call: CallbackQuery) -> None:
    logs = await db.get_requests_log(limit=60)
    if not logs:
        await call.message.answer("Логи заявок пусты.")
        await call.answer()
        return

    await call.message.answer("📚 Последние заявки (лог):")
    for row in logs:
        username = row["username"] or "без username"
        msg = (
            f"#{row['id']} | {row['service_title']} | {row['status']}\n"
            f"user_id: {row['user_id']} | @{username}\n"
            f"Тариф: {int(row['selected_days'] or 0)} дн. / {_fmt_price(float(row['selected_price_usdt'] or 0))} USDT\n"
            f"Создана: {_fmt_iso(row['created_at'])}\n"
            f"Одобрена: {_fmt_iso(row['approved_at'])}\n"
            f"Истекает: {_fmt_iso(row['expires_at'])}\n"
            f"Текст: {row['text_content']}"
        )
        await call.message.answer(msg)
    await call.answer("Логи отправлены.")


@router.callback_query(F.data == "admin:broadcasts")
async def admin_broadcasts(call: CallbackQuery) -> None:
    await call.message.edit_text(
        "Управление рассылками:",
        reply_markup=admin_broadcast_menu_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_bc:create")
async def broadcast_create_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.bc_chat)
    await call.message.answer(
        "Введите target chat ID (например, -1001234567890):",
        reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
    )
    await call.answer()


@router.message(AdminStates.bc_chat)
async def broadcast_set_chat(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        chat_id = int(text)
    except ValueError:
        await message.answer(
            "Неверный chat ID. Введите целое число.",
            reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
        )
        return
    await state.update_data(target_chat_id=chat_id)
    await state.set_state(AdminStates.bc_thread)
    await message.answer(
        "Введите thread ID или 0, если не нужен:",
        reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
    )


@router.message(AdminStates.bc_thread)
async def broadcast_set_thread(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        thread = int(text)
    except ValueError:
        await message.answer(
            "Неверный thread ID. Введите число.",
            reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
        )
        return
    await state.update_data(target_thread_id=None if thread == 0 else thread)
    await state.set_state(AdminStates.bc_interval)
    await message.answer(
        "Введите интервал в минутах:",
        reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
    )


@router.message(AdminStates.bc_interval)
async def broadcast_set_interval(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer(
            "Интервал должен быть положительным целым числом.",
            reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
        )
        return
    await state.update_data(interval_minutes=int(text))
    await state.set_state(AdminStates.bc_text)
    await message.answer(
        "Введите текст рассылки:",
        reply_markup=back_keyboard("adm_bc:cancel", "⬅️ Назад в рассылки"),
    )


@router.message(AdminStates.bc_text)
async def broadcast_set_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    task_id = await db.create_broadcast_task(
        admin_id=message.from_user.id,
        target_chat_id=int(data["target_chat_id"]),
        target_thread_id=data["target_thread_id"],
        interval_minutes=int(data["interval_minutes"]),
        message_text=(message.text or "").strip(),
    )
    await state.clear()
    await message.answer(f"Задача рассылки создана. ID: {task_id}")


@router.callback_query(F.data == "adm_bc:cancel")
async def broadcast_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "Управление рассылками:",
        reply_markup=admin_broadcast_menu_keyboard(),
    )
    await call.answer()


@router.callback_query(F.data == "adm_bc:list")
async def broadcast_list(call: CallbackQuery) -> None:
    tasks = await db.get_broadcast_tasks()
    if not tasks:
        await call.message.answer("Список рассылок пуст.")
        await call.answer()
        return
    for task in tasks[:20]:
        status = "вкл" if int(task["is_enabled"]) else "выкл"
        text = (
            f"Рассылка #{task['id']}\n"
            f"chat_id: {task['target_chat_id']}\n"
            f"thread_id: {task['target_thread_id'] or 0}\n"
            f"Интервал: {task['interval_minutes']} мин\n"
            f"Статус: {status}\n"
            f"Следующий запуск: {task['next_run_at']}"
        )
        await call.message.answer(
            text,
            reply_markup=admin_broadcast_item_keyboard(int(task["id"]), int(task["is_enabled"])),
        )
    await call.answer()


@router.callback_query(F.data.startswith("adm_bc:toggle:"))
async def broadcast_toggle(call: CallbackQuery) -> None:
    task_id = int(call.data.split(":")[2])
    await db.toggle_broadcast_task(task_id)
    await call.answer("Статус рассылки изменен.")


@router.callback_query(F.data.startswith("adm_bc:delete:"))
async def broadcast_delete(call: CallbackQuery) -> None:
    task_id = int(call.data.split(":")[2])
    await db.delete_broadcast_task(task_id)
    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"Рассылка #{task_id} удалена.")
    await call.answer()
