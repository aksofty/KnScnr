import logging
from typing import TypedDict

from genapi import GenAPIClient
from agents.hidden_gems.prompts import PROMPT_AGENT_RESEARCHER, TEMPLATE_USER_RESEARCHER
from agents.hidden_gems.strategist import StrategyResult

logger = logging.getLogger(__name__)

RESEARCHER_SCHEMA = {
    "type": "object",
    "properties": {
        "tmdb_id": {
            "type": "integer",
            "description": "Идентификатор выбранного фильма в TMDB",
        },
        "title": {
            "type": "string",
            "description": "Название выбранного фильма",
        },
        "reasoning": {
            "type": "string",
            "description": "2-3 предложения с обоснованием выбора фильма",
        },
    },
    "additionalProperties": False,
    "required": ["tmdb_id", "title", "reasoning"],
}


class ResearcherResult(TypedDict):
    tmdb_id: int
    title: str
    reasoning: str


async def run_researcher(
    strategy: StrategyResult,
    genapi_client: GenAPIClient,
) -> ResearcherResult:
    """Агент-исследователь: выбирает лучший фильм из выборки кандидатов."""
    messages = [
        {
            "role": "system",
            "content": PROMPT_AGENT_RESEARCHER,
        },
        {
            "role": "user",
            "content": TEMPLATE_USER_RESEARCHER.format(
                creative_concept=strategy["creative_concept"],
                reasoning=strategy["reasoning"],
                candidates_text=strategy["candidates_text"],
            ),
        },
    ]

    result = await genapi_client.generate(
        messages=messages,
        json_format=RESEARCHER_SCHEMA,
    )
    return genapi_client.parse_json_response(result)
