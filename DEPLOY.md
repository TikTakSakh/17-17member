# 🚀 Деплой бота «Ванилька» на сервер

Пошаговая инструкция деплоя на Ubuntu VPS через Docker.

---

## Требования к серверу

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| RAM | 2 ГБ | 4 ГБ |
| Диск | 10 ГБ | 20 ГБ |
| ОС | Ubuntu 22.04+ | Ubuntu 24.04 |

> **Примечание:** Whisper-модель `small` занимает ~1.5 ГБ на диске и ~1.5 ГБ RAM при транскрибации. Если ресурсы ограничены, укажите `WHISPER_MODEL=tiny` в `.env`.

---

## Шаг 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Установка Docker Compose (если нет в составе Docker)
sudo apt install -y docker-compose-plugin

# Перелогинься чтобы применить группу docker
exit
# ... заходим снова
```

Проверяем:
```bash
docker --version
docker compose version
```

---

## Шаг 2. Клонирование проекта

```bash
# Клонируем репозиторий
git clone https://github.com/TikTakSakh/vanilka_webapp_ver3.git vanilka-bot
cd vanilka-bot
```

> Если репозиторий приватный, используйте SSH-ключ или personal access token.

---

## Шаг 3. Настройка окружения

### 3.1 Создание `.env`

```bash
cp .env.example .env
nano .env
```

Заполните все значения:
```env
TELEGRAM_BOT_TOKEN=8483024278:AAG...
OPENAI_API_KEY=sk-or-v1-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
GOOGLE_DRIVE_FILE_ID=1eZ7M_wkqiBW8fb2yCFfT3eg9yxWIud8b
GOOGLE_SERVICE_ACCOUNT_JSON=./service_account.json
MINI_APP_URL=https://TikTakSakh.github.io/web_app/
ADMIN_USER_IDS=771134745
WHISPER_MODEL=small
```

### 3.2 Копирование сервисного аккаунта Google

Скопируйте файл `service_account.json` на сервер в корень проекта:

```bash
# Со своего компьютера:
scp service_account.json user@your-server-ip:~/vanilka-bot/
```

---

## Шаг 4. Сборка и запуск

```bash
# Сборка Docker-образа (первый раз ~5-10 мин)
docker compose build

# Запуск в фоне
docker compose up -d
```

---

## Шаг 5. Проверка

```bash
# Статус контейнера
docker compose ps

# Логи (последние 50 строк, в реальном времени)
docker compose logs -f --tail 50
```

Отправьте `/start` боту в Telegram — он должен ответить приветствием.

---

## Шаг 6. Управление ботом

```bash
# Остановить
docker compose down

# Перезапустить
docker compose restart

# Пересобрать и запустить (после обновления кода)
git pull
docker compose up -d --build
```

---

## Шаг 7. Обновление бота

```bash
cd ~/vanilka-bot
git pull
docker compose up -d --build
```

---

## Устранение проблем

### Бот не стартует
```bash
docker compose logs bot
```
Типичные причины:
- Неверный `TELEGRAM_BOT_TOKEN`
- Не найден `service_account.json`
- Нет доступа к Google Drive файлу

### Whisper не работает (голосовые)
- Проверьте, что `ffmpeg` установлен в контейнере: `docker exec vanilka-bot ffmpeg -version`
- Если мало RAM, смените модель: `WHISPER_MODEL=tiny` в `.env` и пересоберите

### Место на диске
```bash
# Очистка неиспользуемых Docker-образов
docker system prune -a
```
