import asyncio
import logging
import os

from agents.hidden_actors.copyrighter import (
    ActorMovie,
    ActorProfile,
    CopyrighterResult,
    run_copyrighter,
)
from database import Actors, Database
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
ACTOR_COOLDOWN_DAYS = 365
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
OLDEST_MOVIES_LIMIT = 3


def load_env() -> None:
    """Load environment variables from .env when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv()


def check_env_vars(env_vars: tuple[str, ...]) -> bool:
    """Log missing environment variables and return whether all are present."""
    missing_vars = [name for name in env_vars if not os.getenv(name)]
    if not missing_vars:
        return True

    logging.error(
        "Отсутствуют следующие переменные окружения: %s.",
        ", ".join(missing_vars),
    )
    return False


def _collect_photos(person: dict, images: dict) -> list[str]:
    """Собрать ссылки на фото актера."""
    photos = []
    profile_path = person.get("profile_path")
    if profile_path:
        photos.append(f"{TMDB_IMAGE_BASE}{profile_path}")

    for image in images.get("profiles", []):
        file_path = image.get("file_path")
        if file_path:
            photos.append(f"{TMDB_IMAGE_BASE}{file_path}")

    return photos


def _collect_oldest_movies(credits: dict) -> list[ActorMovie]:
    """Взять три самых старых фильма актера по дате релиза."""
    cast = [
        movie for movie in credits.get("cast", []) if movie.get("release_date")
    ]
    cast.sort(key=lambda movie: movie["release_date"])

    return [
        ActorMovie(
            title=movie.get("title") or movie.get("original_title") or "",
            release_date=movie["release_date"],
            character=movie.get("character") or "",
            overview=movie.get("overview") or "",
        )
        for movie in cast[:OLDEST_MOVIES_LIMIT]
    ]


async def collect_actor_profile(
    client: AsyncTMDBClient,
    actor: Actors,
) -> ActorProfile:
    """Собрать данные актера: фото и три самых старых фильма."""
    person, images, credits = await asyncio.gather(
        client.get_person(actor.tmdb_id),
        client.get_person_images(actor.tmdb_id),
        client.get_person_movie_credits(actor.tmdb_id),
    )

    return ActorProfile(
        tmdb_id=actor.tmdb_id,
        name=actor.actor_name,
        rank=actor.rank,
        main_roles=actor.main_roles_count,
        photos=_collect_photos(person, images),
        movies=_collect_oldest_movies(credits),
    )


async def publish_result(result: CopyrighterResult | None) -> None:
    """Опубликовать пост об актере в Telegram."""
    if not result or not result["text"]:
        logging.info("Telegram-пост не отправлен.")
        return

    photos = result["pics"]
    caption = result["text"]

    async with TgPoster(
        bot_token=os.getenv("TG_BOT_TOKEN"),
        channel_id=f"@{os.getenv('TG_CHANNEL_ID')}",
    ) as poster:
        if len(photos) > 1:
            await poster.send_gallery(photos=photos, caption=caption)
        elif photos:
            await poster.send_photo(photo_path_or_url=photos[0], caption=caption)
        else:
            await poster.send_text(caption)

    logging.info("Telegram-пост об актере отправлен.")


async def _run_agents() -> None:
    """Выбрать актера из БД, собрать данные и сгенерировать пост."""
    db = Database(url=os.getenv("DB_URL", DEFAULT_DB_URL))
    await db.init()
    try:
        actor = await db.get_random_actor_due_for_post(
            cooldown_days=ACTOR_COOLDOWN_DAYS
        )
        if actor is None:
            logging.info("Нет актеров, доступных для публикации.")
            return

        logging.info("Выбран актер: %s (tmdb_id=%s)", actor.actor_name, actor.tmdb_id)

        async with GenAPIClient(
            api_key=os.getenv("GENAPI_TOKEN"),
            model=GENAPI_MODEL,
        ) as genapi_client:
            async with AsyncTMDBClient() as client:
                profile = await collect_actor_profile(client, actor)
                result = await run_copyrighter(
                    profile=profile,
                    genapi_client=genapi_client,
                )

        await publish_result(result)
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
