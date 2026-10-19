import asyncio
import logging
import os

from agents.common import check_env_vars, load_env
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


def _collect_photos(person: dict, images: dict) -> list[str]:
    """Собрать основное фото актера и последнее дополнительное."""
    photos = []
    profile_path = person.get("profile_path")
    if profile_path:
        photos.append(f"{TMDB_IMAGE_BASE}{profile_path}")

    profiles = images.get("profiles") or []
    last_path = profiles[-1].get("file_path") if profiles else None
    if last_path and last_path != profile_path:
        photos.append(f"{TMDB_IMAGE_BASE}{last_path}")

    return photos


def _collect_oldest_movies(credits: dict) -> list[ActorMovie]:
    """Взять три самых старых фильма актера по дате релиза."""
    cast = [
        movie for movie in credits.get("cast", []) if movie.get("release_date")
    ]
    cast.sort(key=lambda movie: movie["release_date"])

    movies = []
    for movie in cast[:OLDEST_MOVIES_LIMIT]:
        poster_path = movie.get("poster_path")
        movies.append(
            ActorMovie(
                tmdb_id=movie.get("id", 0),
                title=movie.get("title") or movie.get("original_title") or "",
                release_date=movie["release_date"],
                character=movie.get("character") or "",
                overview=movie.get("overview") or "",
                poster=f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else "",
            )
        )
    return movies


async def _fill_movie_posters(
    client: AsyncTMDBClient,
    movies: list[ActorMovie],
) -> None:
    """Дозагрузить постеры фильмов, которых не оказалось в credits."""
    missing = [movie for movie in movies if not movie["poster"] and movie["tmdb_id"]]
    if not missing:
        return

    details = await asyncio.gather(
        *(client.get_movie(movie["tmdb_id"]) for movie in missing)
    )
    for movie, detail in zip(missing, details):
        poster_path = detail.get("poster_path")
        if poster_path:
            movie["poster"] = f"{TMDB_IMAGE_BASE}{poster_path}"


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

    movies = _collect_oldest_movies(credits)
    await _fill_movie_posters(client, movies)

    return ActorProfile(
        tmdb_id=actor.tmdb_id,
        name=actor.actor_name,
        rank=actor.rank,
        main_roles=actor.main_roles_count,
        photos=_collect_photos(person, images),
        movies=movies,
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
