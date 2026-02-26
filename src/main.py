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
from aiogram.types import MenuButtonDefault

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


    # Reset menu button to default (remove old MenuButtonWebApp)
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())

    # Start polling
    logger.info("Bot is starting polling...")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down...")
        await dialog_history.close()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
