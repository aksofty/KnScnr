# KnScnr (KinoScaner)

Планировщик AI-агентов, которые по расписанию генерируют и публикуют посты в Telegram-канал:

- `hidden_gems` — ежедневно ищет «скрытые жемчужины» кино.
- `hidden_actors` — по выбранным дням недели публикует подборки актёров.

Точка входа — `scheduler.py` (APScheduler). Данные хранятся в SQLite (`tenkino.db`), логи пишутся в `app.log`.

## Требования

- VPS с Linux (Ubuntu/Debian и др.)
- Docker Engine и Docker Compose v2 (`docker compose`)

Установка Docker на чистый сервер:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # затем перелогиньтесь
```

## Быстрый старт на VPS

```bash
# 1. Получить код
git clone https://github.com/aksofty/KnScnr.git KinoScaner
cd KinoScaner

# 2. Создать .env и заполнить секреты
cp .env.example .env
nano .env

# 3. Собрать и запустить в фоне
docker compose up -d --build

# 4. Посмотреть логи
docker compose logs -f
```

Контейнер запускает `scheduler.py` и работает постоянно. Благодаря `restart: unless-stopped`
он поднимается автоматически после перезагрузки сервера и падений.

## Переменные окружения (`.env`)

| Переменная        | Назначение                                              | Пример                          |
| ----------------- | ------------------------------------------------------- | ------------------------------- |
| `TMDB_API_TOKEN`  | Токен TMDB API                                          | `eyJhbGci...`                   |
| `TMDB_BASE_URL`   | Базовый URL TMDB API                                    | `https://api.themoviedb.org/3`  |
| `TMDB_LANGUAGE`   | Язык запросов TMDB                                      | `ru-RU`                         |
| `DB_URL`          | Строка подключения к БД (в Docker переопределяется)     | `sqlite+aiosqlite:///tenkino.db`|
| `GENAPI_TOKEN`    | Токен GenAPI (LLM)                                      | `sk-...`                        |
| `TG_BOT_TOKEN`    | Токен Telegram-бота                                     | `8708697696:AAH...`             |
| `TG_CHANNEL_ID`   | Username канала без `@`                                 | `ten_kino`                      |
| `GEMS_HOUR`/`GEMS_MINS` | Час и минуты запуска `hidden_gems` (минуты — список через запятую) | `18` / `0`        |
| `ACTORS_DAYS`     | Дни недели запуска `hidden_actors`                      | `mon,thu`                       |
| `ACTORS_HOUR`/`ACTORS_MINS` | Час и минуты запуска `hidden_actors` (минуты — список через запятую) | `18` / `0,30`   |

Расписание и все метки времени используют серверное (локальное) время контейнера.

## Данные и логи

В `docker-compose.yml` каталог `./data` на хосте смонтирован в `/app/data` контейнера,
поэтому данные сохраняются при перезапуске и пересборке:

- `./data/tenkino.db` — база данных (SQLite, задаётся через `DB_URL`),
- `./data/app.log` — файл логов.

Логи также дублируются в stdout, поэтому доступны через `docker compose logs`.

## Обслуживание

```bash
# Остановить
docker compose down

# Перезапустить
docker compose restart

# Обновить после изменений в коде
git pull
docker compose up -d --build

# Резервная копия БД и логов
tar czf backup-$(date +%F).tar.gz -C data .
```

## Локальный запуск без Docker

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # заполнить значения
python scheduler.py
```
