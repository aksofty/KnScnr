import asyncio
import logging
import os

from agents.common import check_env_vars, load_env
from agents.hidden_gems.copyrighter import CopyrighterResult, run_copyrighter
from agents.hidden_gems.researcher import ResearcherResult, run_researcher
from agents.hidden_gems.strategist import StrategyResult, run_strategist
from database import Database
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
STRATEGIST_MEMORY_KEYS = (
    "reasoning",
    "creative_concept",
    "with_genres",
    "with_keywords",
)


def publish_result(
    result: CopyrighterResult | None,
    strategist_result: StrategyResult,
    researcher_result: ResearcherResult,
    db: Database,
) -> None:
    """Publish the generated post and persist the agent results."""
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
        else:
            await poster.send_photo(photo_path_or_url=photos[0], caption=caption)

    await db.add_agent_memory(
        data={key: strategist_result[key] for key in STRATEGIST_MEMORY_KEYS}
    )
    await db.add_agent_researcher_memory(
        tmdb_id=researcher_result["tmdb_id"],
        title=researcher_result["title"],
        reasoning=researcher_result["reasoning"],
    )
    await db.add_telegram_post(
        tmdb_id=result["tmdb_id"],
        title=result["title"],
        post_text=caption,
    )
    logging.info("Telegram-пост отправлен.")


async def _run_agents(db: Database) -> None:
    """Run the strategist → researcher → copyrighter pipeline."""
    async with GenAPIClient(
        api_key=os.getenv("GENAPI_TOKEN"),
        model=GENAPI_MODEL,
    ) as genapi_client:
        async with AsyncTMDBClient() as client:
            logging.info("strategist...")
            strategist_result = await run_strategist(
                client=client,
                db=db,
                genapi_client=genapi_client,
            )

            logging.info("researcher...")
            researcher_result = await run_researcher(
                strategy=strategist_result,
                genapi_client=genapi_client,
            )

            logging.info("copyrighter...")
            result = await run_copyrighter(
                tmdb_id=researcher_result["tmdb_id"],
                reasoning=researcher_result["reasoning"],
                client=client,
                genapi_client=genapi_client,
            )
            await publish_result(result, strategist_result, researcher_result, db)


async def main() -> None:
    configure_logging()
    load_env()
    if not check_env_vars(REQUIRED_ENV_VARS):
        return

    db = Database(url=os.getenv("DB_URL"))
    await db.init()
    try:
        logging.info("Запуск агентов: strategist, researcher, copyrighter")
        await _run_agents(db)
        logging.info("Работа агентов завершена.")
    except TMDBError as exc:
        logging.error("Ошибка TMDB: %s", exc)
    except GenAPIError as exc:
        logging.error("Ошибка GenAPI: %s", exc)
    except Exception:
        logging.exception("Произошла ошибка во время работы агентов.")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
