import logging
import random
from typing import TypedDict

from genapi import GenAPIClient
from agents.hidden_gems.prompts import PROMPT_AGENT_COPYRIGHTER, TEMPLATE_USER_COPYRIGHTER
from prompts_loader import load_prompt
from tmdb.async_client import AsyncTMDBClient

logger = logging.getLogger(__name__)

COPYRIGHTER_MODEL = "gemini-3-8-flash"
MAX_PICS = 5
MAX_CAST = 5
MAX_TRAILERS = 1
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

HOOK_STYLES = (
    "Scene / Atmosphere (Начни с атмосферного описания кадра, детали или сцены).",
    "Question / Paradox (Начни с провокационного вопроса, дилеммы или парадокса).",
    "Plot Trigger (Сразу брось читателя в завязку сюжета без предысторий).",
    "Quote / Tagline (Начни с сильной атмосферной фразы, эпиграфа или метафоры).",
    "Backstage / Context (Начни с короткого интересного факта о создании или судьбе фильма).",
)


class CopyrighterResult(TypedDict):
    tmdb_id: int
    title: str
    text: str
    pics: list[str]
    trailer: str | None


def _build_pics(movie: dict, images: dict) -> list[str]:
    """Собрать ссылки на постер и кадры фильма."""
    pics = []
    poster_path = movie.get("poster_path")
    if poster_path:
        pics.append(f"{TMDB_IMAGE_BASE}{poster_path}")

    for backdrop in images.get("backdrops", []):
        file_path = backdrop.get("file_path")
        if file_path:
            pics.append(f"{TMDB_IMAGE_BASE}{file_path}")

    return pics


def _extract_cast(credits: dict) -> list[str]:
    """Взять имена главных актеров."""
    return [actor["name"] for actor in credits.get("cast", [])][:MAX_CAST]


def _extract_trailers(videos: dict) -> list[str]:
    """Извлечь ссылки на трейлеры."""
    return [
        f"https://www.youtube.com/watch?v={video['key']}"
        for video in videos.get("results", [])
    ][:MAX_TRAILERS]


async def _load_videos(client: AsyncTMDBClient, tmdb_id: int) -> dict:
    """Загрузить трейлеры, при пустом ответе повторить запрос на английском."""
    videos = await client.get_movie_videos(tmdb_id)
    if not videos.get("results"):
        videos = await client.get_movie_videos(tmdb_id, language="en-US")
    return videos


async def run_copyrighter(
    tmdb_id: int,
    reasoning: str,
    client: AsyncTMDBClient,
    genapi_client: GenAPIClient,
) -> CopyrighterResult | None:
    """Агент-копирайтер: пишет пост для Telegram на основе данных фильма."""
    if tmdb_id <= 0:
        logger.warning("Некорректный tmdb_id=%s, пост не генерируется.", tmdb_id)
        return None

    movie = await client.get_movie(tmdb_id)
    movie_pics = await client.get_movie_images(tmdb_id)
    movie_credits = await client.get_movie_credits(tmdb_id)
    movie_videos = await _load_videos(client, tmdb_id)

    pics = _build_pics(movie, movie_pics)
    cast = _extract_cast(movie_credits)
    trailers = _extract_trailers(movie_videos)
    trailer = trailers[0] if trailers else None

    messages = [
        {
            "role": "system",
            "content": load_prompt(
                "hidden_gems/PROMPT_AGENT_COPYRIGHTER", PROMPT_AGENT_COPYRIGHTER
            ),
        },
        {
            "role": "user",
            "content": load_prompt(
                "hidden_gems/TEMPLATE_USER_COPYRIGHTER", TEMPLATE_USER_COPYRIGHTER
            ).format(
                title_ru=movie["title"],
                original_title=movie["original_title"],
                release_date=movie["release_date"],
                country=movie["origin_country"],
                cast=",".join(cast),
                genres=", ".join(genre["name"] for genre in movie["genres"]),
                runtime=movie["runtime"],
                rating=movie["vote_average"],
                overview=movie["overview"],
                reasoning=reasoning,
                hook_style=random.choice(HOOK_STYLES),
            ),
        },
    ]

    result = await genapi_client.generate(
        messages=messages,
        model=COPYRIGHTER_MODEL,
    )
    post_text = genapi_client.get_response_content(result)

    if not post_text:
        logger.warning("Копирайтер вернул пустой ответ для tmdb_id=%s.", tmdb_id)
        return None

    return CopyrighterResult(
        tmdb_id=tmdb_id,
        title=movie["title"],
        text=post_text,
        pics=pics[:MAX_PICS],
        trailer=trailer,
    )
