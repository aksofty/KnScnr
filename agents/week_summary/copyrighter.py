import logging
import os

from agents.week_summary.prompts import (
    PROMPT_AGENT_COPYRIGHTER,
    TEMPLATE_USER_COPYRIGHTER,
)
from database import AgentResearcherMemory
from genapi import GenAPIClient
from prompts_loader import load_prompt

logger = logging.getLogger(__name__)

COPYRIGHTER_MODEL = "gemini-3-8-flash"


def _post_url(message_id: int | None) -> str | None:
    """Собрать ссылку на опубликованный пост, если известен его ID."""
    channel_id = os.getenv("TG_CHANNEL_ID")
    if not channel_id or not message_id:
        return None
    return f"https://t.me/{channel_id.lstrip('@')}/{message_id}"


def _format_films(films: list[AgentResearcherMemory]) -> str:
    """Собрать текстовый список фильмов за неделю для промпта."""
    if not films:
        return "Нет данных о фильмах за неделю."

    lines = []
    for film in films:
        created_at = film.created_at.strftime("%d.%m.%Y") if film.created_at else ""
        line = f"- {film.title} ({created_at})"
        if film.reasoning:
            line += f" — {film.reasoning}"
        post_url = _post_url(film.message_id)
        if post_url:
            line += f"\n  Пост: {post_url}"
        lines.append(line)
    return "\n".join(lines)


async def run_copyrighter(
    films: list[AgentResearcherMemory],
    genapi_client: GenAPIClient,
) -> str | None:
    """Агент-копирайтер: пишет пост о фильмах за неделю для Telegram."""
    messages = [
        {
            "role": "system",
            "content": load_prompt(
                "week_summary/PROMPT_AGENT_COPYRIGHTER", PROMPT_AGENT_COPYRIGHTER
            ),
        },
        {
            "role": "user",
            "content": load_prompt(
                "week_summary/TEMPLATE_USER_COPYRIGHTER", TEMPLATE_USER_COPYRIGHTER
            ).format(films=_format_films(films)),
        },
    ]

    result = await genapi_client.generate(
        messages=messages,
        model=COPYRIGHTER_MODEL,
    )
    post_text = genapi_client.get_response_content(result)

    if not post_text:
        logger.warning("Копирайтер вернул пустой ответ для недельной подборки.")
        return None

    return post_text
