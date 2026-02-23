# Telegram-бот «Ванилька»

AI-администратор для магазина бенто-тортов.

## Возможности

- 🎂 Ответы на вопросы о продукции, ценах и доставке
- 💬 Поддержка текстовых сообщений
- 🎤 Распознавание голосовых сообщений (Whisper)
- 📚 База знаний из Google Drive (с авто-обновлением)
- 🧠 Контекст диалога (SQLite)
- 🛒 Мини-приложение для заказов (Telegram WebApp)
- 📊 Статистика и рассылка (для админов)

## Быстрый старт (Docker)

```bash
# 1. Клонировать репозиторий
git clone https://github.com/TikTakSakh/vanilka_webapp_ver3.git && cd vanilka_webapp_ver3

# 2. Настроить окружение
cp .env.example .env
nano .env  # заполнить все значения

# 3. Скопировать service_account.json в корень проекта

# 4. Запустить
docker compose up -d --build
```

> Полная инструкция деплоя на VPS — в [DEPLOY.md](DEPLOY.md)

## Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
python -m src.main
```

## Конфигурация

Скопируйте `.env.example` в `.env` и заполните:

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `OPENAI_API_KEY` | Ключ OpenAI или OpenRouter |
| `OPENAI_BASE_URL` | URL API (для OpenRouter) |
| `GOOGLE_DRIVE_FILE_ID` | ID файла базы знаний |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Путь к `service_account.json` |
| `MINI_APP_URL` | URL мини-приложения |
| `ADMIN_USER_IDS` | ID администраторов (через запятую) |
| `WHISPER_MODEL` | Модель Whisper: `tiny`, `base`, `small` |

## Структура проекта

```
├── src/
│   ├── main.py               # Точка входа
│   ├── config.py              # Конфигурация из .env
│   ├── bot/
│   │   ├── handlers.py        # Обработчики сообщений
│   │   └── middlewares.py     # Логирование и ошибки
│   ├── services/
│   │   ├── llm_service.py     # GPT-4o-mini (OpenRouter)
│   │   ├── transcribe_service.py  # Whisper STT
│   │   ├── knowledge_base.py  # Google Drive
│   │   └── history_logger.py  # Логирование чатов
│   └── storage/
│       ├── dialog_history.py  # Интерфейс истории
│       └── sqlite_history.py  # SQLite-реализация
├── data/                      # База знаний + SQLite DB
├── webapp/                    # Telegram Mini App
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Админ-команды

| Команда | Описание |
|---|---|
| `/stats` | Статистика бота |
| `/reload` | Перезагрузить базу знаний |
| `/broadcast Текст` | Рассылка всем пользователям |
