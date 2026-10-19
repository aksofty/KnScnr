import asyncio
import logging
import os

from agents.common import check_env_vars, load_env
from agents.week_summary.copyrighter import run_copyrighter
from database import AgentResearcherMemory, Database
from genapi import GenAPIClient, GenAPIError
from logging_config import configure_logging
from tg_poster import TgPoster
from tmdb.async_client import AsyncTMDBClient
from tmdb.exceptions import TMDBError


REQUIRED_ENV_VARS = (
    "TMDB_API_TOKEN",
    "DB_URL",
    "GENAPI_TOKEN",
    "TG_BOT_TOKEN",
    "TG_CHANNEL_ID",
)
GENAPI_MODEL = "gpt-4o-mini"
DEFAULT_DB_URL = "sqlite+aiosqlite:///tenkino.db"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_REQUEST_DELAY_SECONDS = 0.5
WEEK_LIMIT = 6


async def _collect_posters(
    client: AsyncTMDBClient,
    films: list[AgentResearcherMemory],
) -> list[str]:
    """Собрать ссылки на постеры фильмов через TMDB с задержкой между запросами."""
    posters = []
    for index, film in enumerate(films):
        if index:
            await asyncio.sleep(TMDB_REQUEST_DELAY_SECONDS)

        movie = await client.get_movie(film.tmdb_id)
        poster_path = movie.get("poster_path")
        if poster_path:
            posters.append(f"{TMDB_IMAGE_BASE}{poster_path}")

    return posters


async def publish_result(text: str | None, photos: list[str] | None = None) -> None:
    """Опубликовать пост о фильмах за неделю в Telegram с постерами."""
    if not text:
        logging.info("Telegram-пост не отправлен.")
        return

    photos = photos or []

    async with TgPoster(
        bot_token=os.getenv("TG_BOT_TOKEN"),
        channel_id=f"@{os.getenv('TG_CHANNEL_ID')}",
    ) as poster:
        if len(photos) > 1:
            sent = await poster.send_gallery(photos=photos, caption=text)
        elif photos:
            sent = await poster.send_photo(photo_path_or_url=photos[0], caption=text)
        else:
            sent = await poster.send_text(text)

    if sent:
        logging.info("Telegram-пост о фильмах за неделю отправлен.")
    else:
        logging.error("Telegram-пост о фильмах за неделю не отправлен.")


async def _run_agents() -> None:
    """Взять последние записи о фильмах и сгенерировать пост о неделе."""
    db = Database(url=os.getenv("DB_URL", DEFAULT_DB_URL))
    await db.init()
    try:
        films = await db.get_agent_researcher_memory(limit=WEEK_LIMIT)
        films.reverse()
        if not films:
            logging.info("Нет записей о фильмах за неделю.")
            return

        logging.info("Собрано записей о фильмах: %d", len(films))

        async with AsyncTMDBClient() as client:
            posters = await _collect_posters(client, films)

        async with GenAPIClient(
            api_key=os.getenv("GENAPI_TOKEN"),
            model=GENAPI_MODEL,
        ) as genapi_client:
            text = await run_copyrighter(
                films=films,
                genapi_client=genapi_client,
            )

        await publish_result(text, posters)
    finally:
        await db.close()


async def main() -> None:
    configure_logging()
    load_env()
    if not check_env_vars(REQUIRED_ENV_VARS):
        return

    try:
        await _run_agents()
    except TMDBError as exc:
        logging.error("Ошибка TMDB: %s", exc)
    except GenAPIError as exc:
        logging.error("Ошибка GenAPI: %s", exc)
    except Exception:
        logging.exception("Произошла ошибка во время работы агента.")


if __name__ == "__main__":
    asyncio.run(main())
