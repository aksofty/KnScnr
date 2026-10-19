import logging
from typing import TypedDict

from agents.hidden_actors.prompts import (
    PROMPT_AGENT_COPYRIGHTER,
    TEMPLATE_USER_COPYRIGHTER,
)
from genapi import GenAPIClient
from prompts_loader import load_prompt

logger = logging.getLogger(__name__)

COPYRIGHTER_MODEL = "gemini-3-8-flash"
MAX_ACTOR_PICS = 2
MAX_MOVIE_POSTERS = 3


class ActorMovie(TypedDict):
    tmdb_id: int
    title: str
    release_date: str
    character: str
    overview: str
    poster: str


class ActorProfile(TypedDict):
    tmdb_id: int
    name: str
    rank: int
    main_roles: int
    photos: list[str]
    movies: list[ActorMovie]


class CopyrighterResult(TypedDict):
    tmdb_id: int
    name: str
    text: str
    pics: list[str]


def _format_actor_data(profile: ActorProfile) -> str:
    """Собрать текстовое описание данных актера для промпта."""
    return (
        f"Ранг: {profile['rank']}\n"
        f"Главных ролей в топ-фильмах: {profile['main_roles']}\n"
        f"TMDB ID: {profile['tmdb_id']}"
    )


def _format_movies(movies: list[ActorMovie]) -> str:
    """Собрать текстовый список фильмов актера для промпта."""
    if not movies:
        return "Нет данных о фильмах."

    lines = []
    for movie in movies:
        line = f"- {movie['title']} ({movie['release_date']})"
        if movie["character"]:
            line += f", роль: {movie['character']}"
        lines.append(line)
    return "\n".join(lines)


async def run_copyrighter(
    profile: ActorProfile,
    genapi_client: GenAPIClient,
) -> CopyrighterResult | None:
    """Агент-копирайтер: пишет пост об актере для Telegram."""
    messages = [
        {
            "role": "system",
            "content": load_prompt(
                "hidden_actors/PROMPT_AGENT_COPYRIGHTER", PROMPT_AGENT_COPYRIGHTER
            ),
        },
        {
            "role": "user",
            "content": load_prompt(
                "hidden_actors/TEMPLATE_USER_COPYRIGHTER", TEMPLATE_USER_COPYRIGHTER
            ).format(
                actor_name=profile["name"],
                actor_data=_format_actor_data(profile),
                movies=_format_movies(profile["movies"]),
                photos="\n".join(profile["photos"]) or "Нет фото.",
            ),
        },
    ]

    result = await genapi_client.generate(
        messages=messages,
        model=COPYRIGHTER_MODEL,
    )
    post_text = genapi_client.get_response_content(result)

    if not post_text:
        logger.warning("Копирайтер вернул пустой ответ для актера %s.", profile["name"])
        return None

    movie_posters = [
        movie["poster"] for movie in profile["movies"] if movie["poster"]
    ]
    pics = (
        profile["photos"][:MAX_ACTOR_PICS]
        + movie_posters[:MAX_MOVIE_POSTERS]
    )

    return CopyrighterResult(
        tmdb_id=profile["tmdb_id"],
        name=profile["name"],
        text=post_text,
        pics=pics,
    )
