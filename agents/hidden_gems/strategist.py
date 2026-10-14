import datetime
import logging
from typing import Any, TypedDict

from database import Database
from genapi import GenAPIClient
from agents.hidden_gems.prompts import PROMPT_AGENT_STRATEGIST, TEMPLATE_USER_STRATEGIST
from tmdb.async_client import AsyncTMDBClient
from utils import get_candidates, get_genres_string

logger = logging.getLogger(__name__)

DAYS_RU = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)

DISCOVER_PARAMS: dict[str, Any] = {
    "include_adult": "False",
    "include_video": "False",
    "vote_average.gte": 6.5,
    "vote_average.lte": 8.5,
    "vote_count.gte": 100.0,
    "vote_count.lte": 2000.0,
    "sort_by": "vote_average.desc",
    "without_keywords": "210024",  # anime
    "page": "1",
}

CANDIDATES_PAGE_LIMIT = 10
BLACKLIST_LIMIT = 100
HISTORY_LIMIT = 3

STRATEGIST_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Краткое обоснование выбора темы (с указанием праздника из списка разрешенных или логики дня недели)",
        },
        "creative_concept": {
            "type": "string",
            "description": "Описание идеи для сегодняшнего поста",
        },
        "with_genres": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Названия жанров на английском через запятую",
        },
        "with_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ключевые слова для поиска на английском через запятую",
        },
    },
    "additionalProperties": False,
    "required": [
        "reasoning",
        "creative_concept",
        "with_genres",
        "with_keywords",
    ],
}


class StrategyResult(TypedDict):
    reasoning: str
    creative_concept: str
    with_genres: list[str]
    with_keywords: list[str]
    candidates_text: str


def _format_history(history: list[Any]) -> str:
    """Сформировать текст истории публикаций для промпта."""
    if not history:
        return "История пока пуста."

    lines = []
    for item in history:
        date_str = item.created_at.strftime("%d.%m.%Y %H:%M:%S")
        lines.append(f"{date_str}: {item.data}")
    return "\n".join(lines)


async def run_strategist(
    client: AsyncTMDBClient,
    genapi_client: GenAPIClient,
    db: Database,
) -> StrategyResult:
    """Агент-стратег: выбирает жанры и ключевые слова и собирает выборку кандидатов."""
    now = datetime.datetime.now()
    history = await db.get_agent_memory(limit=HISTORY_LIMIT)

    messages = [
        {
            "role": "system",
            "content": PROMPT_AGENT_STRATEGIST,
        },
        {
            "role": "user",
            "content": TEMPLATE_USER_STRATEGIST.format(
                current_date=now.strftime("%Y-%m-%d"),
                day_of_week=DAYS_RU[now.weekday()],
                current_time=now.strftime("%H:%M"),
                history_text=_format_history(history),
            ),
        },
    ]

    result = await genapi_client.generate(
        messages=messages,
        json_format=STRATEGIST_SCHEMA,
    )
    concept = genapi_client.parse_json_response(result)

    keyword_ids = await client.keywords_search(concept["with_keywords"])
    with_keywords = "|".join(map(str, keyword_ids))

    with_genres = get_genres_string(concept["with_genres"])
    logger.debug("Жанры %s -> %s", concept["with_genres"], with_genres)

    params = dict(DISCOVER_PARAMS)
    params["with_keywords"] = with_keywords
    params["with_genres"] = with_genres

    candidates_text = await get_candidates(
        client=client,
        db=db,
        params=params,
        page_limit=CANDIDATES_PAGE_LIMIT,
        blacklist_limit=BLACKLIST_LIMIT,
    )

    return StrategyResult(
        reasoning=concept["reasoning"],
        creative_concept=concept["creative_concept"],
        with_genres=concept["with_genres"],
        with_keywords=concept["with_keywords"],
        candidates_text=candidates_text,
    )
