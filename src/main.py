"""Main entry point for the 17/17 bar Telegram bot."""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonDefault, MenuButtonWebApp, WebAppInfo

from src.bot.handlers import router, setup_services
from src.bot.middlewares import ErrorHandlingMiddleware, LoggingMiddleware
from src.config import load_config
from src.services.knowledge_base import KnowledgeBaseService
from src.services.llm_service import LLMService
from src.services.transcribe_service import TranscribeService
from src.services.history_logger import HistoryLogger
from src.storage.sqlite_history import SQLiteDialogHistory

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _setup_logging() -> None:
    """Configure logging with both stdout and rotating file handler."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(stdout_handler)

    # Rotating file handler
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "bar1717.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(file_handler)


logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize and run the bot."""
    _setup_logging()
    logger.info("Starting 17/17 bar bot...")

    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded successfully")
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(1)

    # Get absolute path for cache
    project_root = Path(__file__).parent.parent
    cache_path = project_root / config.knowledge_base_cache_path
    db_path = project_root / config.db_path

    # Initialize services
    dialog_history = SQLiteDialogHistory(
        db_path=db_path,
        max_messages=config.max_history_messages,
    )
    await dialog_history.init()

    llm_service = LLMService(
        api_key=config.openai_api_key,
        base_url=config.openai_base_url,
    )

    transcribe_service = TranscribeService(
        model_name=config.whisper_model,
    )

    history_logger = HistoryLogger()

    knowledge_base_service = KnowledgeBaseService(
        file_id=config.google_drive_file_id,
        service_account_path=config.google_service_account_json,
        cache_path=cache_path,
    )

    # Load knowledge base
    logger.info("Loading knowledge base...")
    knowledge_content = await knowledge_base_service.load()
    if knowledge_content:
        llm_service.update_knowledge_base(knowledge_content)
        logger.info("Knowledge base loaded: %d characters", len(knowledge_content))
    else:
        logger.warning("Knowledge base is empty or failed to load")

    # Setup handlers with services
    setup_services(
        llm=llm_service,
        transcribe=transcribe_service,
        history=dialog_history,
        logger_service=history_logger,
        kb_service=knowledge_base_service,
        admins=config.admin_user_ids,
        webapp_url=config.mini_app_url,
    )

    # Initialize bot and dispatcher
    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Register middlewares
    dp.message.outer_middleware(LoggingMiddleware())
    dp.message.outer_middleware(ErrorHandlingMiddleware())

    # Include routers
    dp.include_router(router)


    # Reset menu button to default
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    # Clear any previously registered command menu
    await bot.delete_my_commands()

    # Define aiohttp web app for Mini App notifications
    from aiohttp import web

    async def handle_notify(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            room = data.get("room", "Неизвестная комната")
            command = data.get("command", "")
            user_data = data.get("user", {})
            user_id = user_data.get("id")
            user_name = user_data.get("name", "Гость")
            
            clean_command = command.lstrip("> ").strip()
            
            # 1. Send confirmation to the user
            if user_id:
                try:
                    await bot.send_message(
                        user_id,
                        f"✅ Запрос отправлен!\n� Комната: <b>{room}</b>\n📌 {clean_command}",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.warning("Could not send confirmation to user %s: %s", user_id, e)
                    
                # Log to history
                if history_logger:
                    history_logger.log_message(
                        user_id,
                        f"{room} просит {clean_command}",
                        user_name
                    )
            
            # 2. Notify all admins
            notification_text = f"🔔 <b>{room}</b> просит <b>{clean_command}</b>"
            admin_ids = await dialog_history.get_notification_admin_ids()
            
            success_count = 0
            for admin_id in admin_ids:
                try:
                    await bot.send_message(admin_id, notification_text, parse_mode=ParseMode.HTML)
                    success_count += 1
                except Exception as e:
                    logger.error("Failed to notify admin %s: %s", admin_id, e)
                    
            return web.json_response({
                "ok": True, 
                "notified": success_count,
                "total_admins": len(admin_ids)
            })
            
        except Exception as e:
            logger.error("Error in /notify: %s", e)
            return web.json_response({"ok": False, "error": str(e)}, status=400)

    app = web.Application()
    
    # Configure CORS for the API
    import aiohttp_cors
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    
    resource = cors.add(app.router.add_resource("/notify"))
    cors.add(resource.add_route("POST", handle_notify))

    runner = web.AppRunner(app)
    await runner.setup()
    
    # Run API server on port 8080 (or configurable if needed)
    port = 8080
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    logger.info("Starting API server on port %s...", port)
    await site.start()

    # Start polling
    logger.info("Bot is starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await runner.cleanup()
        await dialog_history.close()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())

