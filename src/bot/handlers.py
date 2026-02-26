"""Telegram message handlers."""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    KeyboardButton,
    MenuButtonDefault,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from beartype import beartype

from src.services.llm_service import LLMService
from src.services.transcribe_service import TranscribeService
from src.services.knowledge_base import KnowledgeBaseService
from src.services.history_logger import HistoryLogger
from src.storage.sqlite_history import SQLiteDialogHistory

logger = logging.getLogger(__name__)

router = Router(name="main")

# These will be injected at startup
llm_service: LLMService | None = None
transcribe_service: TranscribeService | None = None
dialog_history: SQLiteDialogHistory | None = None
history_logger: HistoryLogger | None = None
knowledge_base_service: KnowledgeBaseService | None = None
admin_user_ids: list[int] = []
_bot_start_time: datetime = datetime.now()
mini_app_url: str | None = None


@beartype
def setup_services(
    llm: LLMService,
    transcribe: TranscribeService,
    history: SQLiteDialogHistory,
    logger_service: HistoryLogger,
    kb_service: KnowledgeBaseService,
    admins: list[int] | None = None,
    webapp_url: str | None = None,
) -> None:
    """Setup services for handlers."""
    global llm_service, transcribe_service, dialog_history, history_logger
    global knowledge_base_service, admin_user_ids, _bot_start_time, mini_app_url
    llm_service = llm
    transcribe_service = transcribe
    dialog_history = history
    history_logger = logger_service
    knowledge_base_service = kb_service
    admin_user_ids = admins or []
    mini_app_url = webapp_url
    _bot_start_time = datetime.now()


WELCOME_MESSAGE = """Привет! 👋 Добро пожаловать в бар «17/17»!

🍸 Я помогу вам сориентироваться в нашем меню, ценах и услугах.

Просто напишите мне ваш вопрос или отправьте голосовое сообщение."""


# ── Helpers ──────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    """Check if a user is an admin."""
    return user_id in admin_user_ids


# ── /start ───────────────────────────────────────────────────

@router.message(CommandStart())
async def command_start_handler(message: Message, bot: Bot) -> None:
    """Handle /start command with welcome message and catalog button."""
    # Force reset menu button for this specific chat (clears cached MenuButtonWebApp)
    await bot.set_chat_menu_button(
        chat_id=message.chat.id,
        menu_button=MenuButtonDefault()
    )

    # Build reply keyboard with web app button
    if mini_app_url:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="🚨 Кнопка вызова",
                        web_app=WebAppInfo(url=mini_app_url),
                    ),
                    KeyboardButton(text="📞 Поддержка"),
                ]
            ],
            resize_keyboard=True,
        )
        await message.answer(WELCOME_MESSAGE, reply_markup=keyboard)
    else:
        await message.answer(WELCOME_MESSAGE)

    if message.from_user and dialog_history:
        await dialog_history.upsert_user(
            message.from_user.id, message.from_user.username
        )
        await dialog_history.clear(message.from_user.id)

    if history_logger and message.from_user:
        history_logger.log_message(
            message.from_user.id, "/start", message.from_user.username
        )


# ── Поддержка ────────────────────────────────────────────────

SUPPORT_MESSAGE = """📞 <b>Поддержка</b>

Свяжитесь с нами любым удобным способом:

📱 Свяжитесь с администратором бара «17/17»
💬 Telegram: напишите нам

⏰ <i>Уточняйте график работы у администратора</i>"""


@router.message(F.text == "📞 Поддержка")
async def support_handler(message: Message) -> None:
    """Handle Поддержка button press."""
    await message.answer(SUPPORT_MESSAGE)


# ── /help ────────────────────────────────────────────────────

@router.message(Command("help"))
async def command_help_handler(message: Message) -> None:
    """Show available commands."""
    user_commands = (
        "📋 <b>Доступные команды:</b>\n\n"
        "/start — Перезапустить бота\n"
        "/help — Список команд\n"
        "/menu — Меню бара\n"
        "/reset — Сбросить историю диалога"
    )

    if message.from_user and _is_admin(message.from_user.id):
        admin_commands = (
            "\n\n🔐 <b>Админ-команды:</b>\n\n"
            "/stats — Статистика бота\n"
            "/users — Список пользователей\n"
            "/history &lt;user_id&gt; — История переписки\n"
            "/ban &lt;user_id&gt; — Заблокировать\n"
            "/unban &lt;user_id&gt; — Разблокировать\n"
            "/broadcast &lt;текст&gt; — Рассылка\n"
            "/reload — Обновить базу знаний\n"
            "/system &lt;текст&gt; — Сменить промпт\n"
            "/setadmin &lt;user_id&gt; — Назначить получателя уведомлений\n"
            "/export — Экспорт данных"
        )
        await message.answer(user_commands + admin_commands)
    else:
        await message.answer(user_commands)


# ── /menu ────────────────────────────────────────────────────

@router.message(Command("menu"))
async def command_menu_handler(message: Message) -> None:
    """Show bar menu from knowledge base."""
    if not knowledge_base_service:
        await message.answer("Меню ещё не загружено. Попробуйте позже.")
        return

    content = knowledge_base_service.content
    if not content:
        await message.answer("Меню пока не доступно. Попробуйте позже.")
        return

    # Telegram message limit is 4096 chars
    if len(content) > 4000:
        # Send as multiple messages
        chunks = [content[i:i+4000] for i in range(0, len(content), 4000)]
        for i, chunk in enumerate(chunks):
            prefix = f"📖 <b>Меню бара (часть {i+1}/{len(chunks)}):</b>\n\n" if len(chunks) > 1 else "📖 <b>Меню бара:</b>\n\n"
            await message.answer(prefix + chunk)
    else:
        await message.answer(f"📖 <b>Меню бара:</b>\n\n{content}")


# ── /reset ───────────────────────────────────────────────────

@router.message(Command("reset"))
async def command_reset_handler(message: Message) -> None:
    """Reset conversation history for the user."""
    if not message.from_user or not dialog_history:
        return

    await dialog_history.clear(message.from_user.id)
    await message.answer(
        "🔄 История диалога очищена. Можете начать разговор заново!"
    )


# ── Admin: /stats ────────────────────────────────────────────

@router.message(Command("stats"))
async def command_stats_handler(message: Message) -> None:
    """Show bot statistics (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    stats = await dialog_history.get_stats()
    uptime = datetime.now() - _bot_start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"💬 Сообщений всего: <b>{stats['total_messages']}</b>\n"
        f"📝 От пользователей: <b>{stats['user_messages']}</b>\n"
        f"🟢 Активных сегодня: <b>{stats['active_today']}</b>\n"
        f"⏱ Аптайм: <b>{hours}ч {minutes}м {seconds}с</b>"
    )
    await message.answer(text)


# ── Admin: /reload ───────────────────────────────────────────

@router.message(Command("reload"))
async def command_reload_handler(message: Message) -> None:
    """Reload knowledge base from Google Drive (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not knowledge_base_service or not llm_service:
        await message.answer("Сервисы ещё не инициализированы.")
        return

    await message.answer("🔄 Перезагружаю базу знаний...")

    content = await knowledge_base_service.load()
    if content:
        llm_service.update_knowledge_base(content)
        await message.answer(
            f"✅ База знаний обновлена ({len(content)} символов)"
        )
    else:
        await message.answer("⚠️ Не удалось загрузить базу знаний")


# ── Admin: /broadcast ────────────────────────────────────────

@router.message(Command("broadcast"))
async def command_broadcast_handler(message: Message, bot: Bot) -> None:
    """Broadcast a message to all known users (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    # Extract broadcast text after "/broadcast "
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        await message.answer(
            "Использование: <code>/broadcast Текст сообщения</code>"
        )
        return

    user_ids = await dialog_history.get_all_user_ids()
    sent = 0
    failed = 0

    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 Рассылка завершена\n"
        f"✅ Доставлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )


# ── Admin: /users ────────────────────────────────────────────

@router.message(Command("users"))
async def command_users_handler(message: Message) -> None:
    """Show list of all users (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    users = await dialog_history.get_all_users()
    if not users:
        await message.answer("Пользователей пока нет.")
        return

    lines = [f"👥 <b>Пользователи ({len(users)}):</b>\n"]
    for i, u in enumerate(users, 1):
        banned = " 🚫" if u["is_banned"] else ""
        username = f"@{u['username']}" if u['username'] else "—"
        last_seen = u["last_seen"][:10] if u["last_seen"] else "—"
        lines.append(
            f"{i}. <code>{u['user_id']}</code> | {username} | "
            f"💬{u['msg_count']} | 📅{last_seen}{banned}"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        # Send as file if too long
        file = BufferedInputFile(
            text.encode("utf-8"), filename="users.txt"
        )
        await message.answer_document(file, caption="👥 Список пользователей")
    else:
        await message.answer(text)


# ── Admin: /history <user_id> ────────────────────────────────

@router.message(Command("history"))
async def command_history_handler(message: Message) -> None:
    """Show message history for a specific user (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    # Parse user_id from command
    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "Использование: <code>/history &lt;user_id&gt;</code>"
        )
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Используйте число.")
        return

    history = await dialog_history.get_user_history(target_user_id)
    if not history:
        await message.answer(f"История пользователя <code>{target_user_id}</code> пуста.")
        return

    lines = [f"💬 <b>История пользователя</b> <code>{target_user_id}</code>:\n"]
    for msg in history:
        role_icon = "👤" if msg["role"] == "user" else "🤖"
        time_str = msg["created_at"][11:16] if msg["created_at"] and len(msg["created_at"]) > 16 else ""
        content_preview = msg["content"][:100]
        if len(msg["content"]) > 100:
            content_preview += "..."
        lines.append(f"{role_icon} [{time_str}] {content_preview}")

    text = "\n".join(lines)
    if len(text) > 4000:
        file = BufferedInputFile(
            text.encode("utf-8"), filename=f"history_{target_user_id}.txt"
        )
        await message.answer_document(file, caption=f"💬 История пользователя {target_user_id}")
    else:
        await message.answer(text)


# ── Admin: /ban <user_id> ───────────────────────────────────

@router.message(Command("ban"))
async def command_ban_handler(message: Message) -> None:
    """Ban a user (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "Использование: <code>/ban &lt;user_id&gt;</code>"
        )
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return

    if target_user_id in admin_user_ids:
        await message.answer("❌ Нельзя заблокировать администратора.")
        return

    await dialog_history.ban_user(target_user_id)
    await message.answer(f"🚫 Пользователь <code>{target_user_id}</code> заблокирован.")


# ── Admin: /unban <user_id> ─────────────────────────────────

@router.message(Command("unban"))
async def command_unban_handler(message: Message) -> None:
    """Unban a user (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer(
            "Использование: <code>/unban &lt;user_id&gt;</code>"
        )
        return

    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный формат user_id.")
        return

    await dialog_history.unban_user(target_user_id)
    await message.answer(f"✅ Пользователь <code>{target_user_id}</code> разблокирован.")


# ── Admin: /system <text> ───────────────────────────────────

@router.message(Command("system"))
async def command_system_handler(message: Message) -> None:
    """Change or reset the system prompt (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not llm_service:
        await message.answer("Сервис LLM ещё не инициализирован.")
        return

    text = (message.text or "").partition(" ")[2].strip()

    if not text:
        # Show current prompt preview
        preview = llm_service.get_current_system_prompt_preview()
        await message.answer(
            f"🧠 <b>Текущий системный промпт:</b>\n\n"
            f"<code>{preview}</code>\n\n"
            "Использование:\n"
            "<code>/system Новый промпт</code> — установить\n"
            "<code>/system reset</code> — сбросить"
        )
        return

    if text.lower() == "reset":
        llm_service.reset_system_prompt()
        await message.answer("✅ Системный промпт сброшен на стандартный.")
    else:
        llm_service.set_custom_system_prompt(text)
        await message.answer(
            f"✅ Системный промпт обновлён.\n\n"
            f"<code>{text[:200]}{'...' if len(text) > 200 else ''}</code>"
        )


# ── Admin: /export ──────────────────────────────────────────

@router.message(Command("export"))
async def command_export_handler(message: Message) -> None:
    """Export bot data as a text file (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    await message.answer("📦 Формирую экспорт...")

    report = await dialog_history.export_data()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file = BufferedInputFile(
        report.encode("utf-8"), filename=f"export_{timestamp}.txt"
    )
    await message.answer_document(file, caption="📦 Экспорт данных бота")


# ── Admin: /setadmin ────────────────────────────────────────

@router.message(Command("setadmin"))
async def command_setadmin_handler(message: Message) -> None:
    """Add or remove a notification admin (admin only)."""
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    if not dialog_history:
        await message.answer("Хранилище ещё не инициализировано.")
        return

    args = (message.text or "").split()

    if len(args) < 2:
        # Show current notification admins
        current = await dialog_history.get_notification_admin_ids()
        if current:
            ids_text = "\n".join(f"• <code>{uid}</code>" for uid in current)
            await message.answer(
                f"🔔 <b>Получатели уведомлений:</b>\n\n{ids_text}\n\n"
                "Использование:\n"
                "<code>/setadmin &lt;user_id&gt;</code> — добавить\n"
                "<code>/setadmin remove &lt;user_id&gt;</code> — удалить"
            )
        else:
            await message.answer(
                "🔔 Получателей уведомлений пока нет.\n\n"
                "Использование:\n"
                "<code>/setadmin &lt;user_id&gt;</code> — добавить\n"
                "<code>/setadmin remove &lt;user_id&gt;</code> — удалить"
            )
        return

    if args[1].lower() == "remove":
        if len(args) < 3:
            await message.answer("Использование: <code>/setadmin remove &lt;user_id&gt;</code>")
            return
        try:
            target_id = int(args[2])
        except ValueError:
            await message.answer("❌ Неверный формат user_id.")
            return
        await dialog_history.remove_notification_admin(target_id)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> удалён из получателей уведомлений.")
    else:
        try:
            target_id = int(args[1])
        except ValueError:
            await message.answer("❌ Неверный формат user_id.")
            return
        await dialog_history.add_notification_admin(target_id)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> добавлен как получатель уведомлений.")


# ── Text messages ────────────────────────────────────────────

@router.message(F.text)
async def text_message_handler(message: Message) -> None:
    """Handle text messages by sending to LLM."""
    if not message.text or not message.from_user:
        return

    if not llm_service or not dialog_history:
        await message.answer("Бот ещё не полностью загружен. Попробуйте позже.")
        return

    user_id = message.from_user.id

    # Check ban
    if await dialog_history.is_banned(user_id):
        return

    # Register/update user
    await dialog_history.upsert_user(user_id, message.from_user.username)

    # Log user message
    if history_logger:
        history_logger.log_message(user_id, message.text, message.from_user.username)

    # Get conversation history
    history = await dialog_history.get_history(user_id)

    # Generate response
    response = await llm_service.generate_response(message.text, history)

    # Save messages to history
    await dialog_history.add_message(user_id, "user", message.text)
    await dialog_history.add_message(user_id, "assistant", response)

    await message.answer(response)


# ── Voice messages ───────────────────────────────────────────

@router.message(F.voice)
async def voice_message_handler(message: Message, bot: Bot) -> None:
    """Handle voice messages by transcribing and sending to LLM."""
    if not message.voice or not message.from_user:
        return

    if not llm_service or not transcribe_service or not dialog_history:
        await message.answer("Бот ещё не полностью загружен. Попробуйте позже.")
        return

    user_id = message.from_user.id

    # Check ban
    if await dialog_history.is_banned(user_id):
        return

    await dialog_history.upsert_user(user_id, message.from_user.username)

    # Show typing indicator
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        file = await bot.get_file(message.voice.file_id)
        if not file.file_path:
            await message.answer("Не удалось получить голосовое сообщение.")
            return

        file_data = await bot.download_file(file.file_path)
        if not file_data:
            await message.answer("Не удалось скачать голосовое сообщение.")
            return

        audio_bytes = file_data.read()

        # Transcribe
        transcribed_text = await transcribe_service.transcribe(audio_bytes, "ogg")

        if not transcribed_text:
            await message.answer(
                "Не удалось распознать голосовое сообщение. "
                "Попробуйте отправить его ещё раз или напишите текстом."
            )
            return

        logger.info("Transcribed voice from user %d: %s", user_id, transcribed_text[:50])

        # Get conversation history
        history = await dialog_history.get_history(user_id)

        # Generate response
        response = await llm_service.generate_response(transcribed_text, history)

        # Save messages
        await dialog_history.add_message(user_id, "user", transcribed_text)
        await dialog_history.add_message(user_id, "assistant", response)

        await message.answer(response)

        if history_logger:
            history_logger.log_message(user_id, transcribed_text, message.from_user.username)

    except Exception as e:
        logger.error("Error processing voice message: %s", e)
        await message.answer(
            "Произошла ошибка при обработке голосового сообщения. Попробуйте позже."
        )


# ── Web App data ─────────────────────────────────────────────

@router.message(F.web_app_data)
async def web_app_data_handler(message: Message, bot: Bot) -> None:
    """Handle data from Telegram Mini App (commands and orders)."""
    if not message.web_app_data:
        return

    logger.info("Received web_app_data: %s", message.web_app_data.data[:200])

    try:
        data = json.loads(message.web_app_data.data)

        if data.get("type") == "command":
            room = data.get("room", "")
            command_text = data.get("text", "")

            if room and command_text:
                # Clean command text: remove ">> " prefix if present
                clean_command = command_text.lstrip("> ").strip()

                # Confirm to the user
                await message.answer(
                    f"✅ Запрос отправлен!\n"
                    f"📍 Комната: <b>{room}</b>\n"
                    f"📌 {clean_command}"
                )

                # Forward notification to all notification admins
                if dialog_history:
                    notify_ids = await dialog_history.get_notification_admin_ids()
                    notification_text = f"🔔 <b>{room}</b> просит <b>{clean_command}</b>"

                    for admin_id in notify_ids:
                        try:
                            await bot.send_message(admin_id, notification_text)
                        except Exception as e:
                            logger.error("Failed to notify admin %d: %s", admin_id, e)

                # Log to history
                if history_logger and message.from_user:
                    history_logger.log_message(
                        message.from_user.id,
                        f"{room} просит {clean_command}",
                        message.from_user.username,
                    )

                logger.info(
                    "WebApp command: room=%s, command=%s, user=%s",
                    room, clean_command,
                    message.from_user.id if message.from_user else "?",
                )

        elif data.get("type") == "order":
            items = data.get("items", [])
            total_price = data.get("total", 0)

            text_lines = ["🛒 <b>Ваш заказ:</b>\n"]
            for idx, item in enumerate(items, 1):
                name = item.get("name", "Товар")
                qty = item.get("quantity", 1)
                text_lines.append(f"{idx}. {name} x {qty} шт.")

            text_lines.append(f"\nна сумму <b>{total_price} руб.</b>")

            pickup_date = data.get("pickup_date", "")
            pickup_time = data.get("pickup_time", "")
            if pickup_date and pickup_time:
                parts = pickup_date.split("-")
                if len(parts) == 3:
                    date_formatted = f"{parts[2]}.{parts[1]}.{parts[0]}"
                else:
                    date_formatted = pickup_date
                text_lines.append(f"будет ждать вас <b>{date_formatted}</b> к <b>{pickup_time}</b>")

            text_lines.append("\n🙏 <i>Спасибо за заказ!</i>")

            order_text = "\n".join(text_lines)
            await message.answer(order_text)

            if history_logger and message.from_user:
                history_lines = ["Заказ:\n"]
                for idx, item in enumerate(items, 1):
                    name = item.get("name", "Товар")
                    qty = item.get("quantity", 1)
                    history_lines.append(f"{idx}. {name} x {qty} шт.")
                history_lines.append(f"\nна сумму {total_price} руб.")
                if pickup_date and pickup_time:
                    history_lines.append(f"будет ждать вас {date_formatted} к {pickup_time}")
                history_logger.log_message(
                    message.from_user.id,
                    "\n".join(history_lines),
                    message.from_user.username,
                )

    except json.JSONDecodeError:
        await message.answer("Ошибка при обработке данных. Попробуйте ещё раз.")
    except Exception as e:
        logger.error("Error processing web_app_data: %s", e)
        await message.answer("Произошла ошибка при обработке запроса.")
