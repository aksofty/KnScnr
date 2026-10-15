import asyncio
import logging
import os

from agents.week_summary.copyrighter import run_copyrighter
from database import Database
from genapi import GenAPIClient, GenAPIError
from logging_config import configure_logging
from tg_poster import TgPoster


REQUIRED_ENV_VARS = (
    "DB_URL",
    "GENAPI_TOKEN",
    "TG_BOT_TOKEN",
    "TG_CHANNEL_ID",
)
GENAPI_MODEL = "gpt-4o-mini"
DEFAULT_DB_URL = "sqlite+aiosqlite:///tenkino.db"
WEEK_LIMIT = 7


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


async def publish_result(text: str | None) -> None:
    """Опубликовать текстовый пост о фильмах за неделю в Telegram (без фото)."""
    if not text:
        logging.info("Telegram-пост не отправлен.")
        return

    async with TgPoster(
        bot_token=os.getenv("TG_BOT_TOKEN"),
        channel_id=f"@{os.getenv('TG_CHANNEL_ID')}",
    ) as poster:
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
        if not films:
            logging.info("Нет записей о фильмах за неделю.")
            return

        logging.info("Собрано записей о фильмах: %d", len(films))

        async with GenAPIClient(
            api_key=os.getenv("GENAPI_TOKEN"),
            model=GENAPI_MODEL,
        ) as genapi_client:
            text = await run_copyrighter(
                films=films,
                genapi_client=genapi_client,
            )

        await publish_result(text)
    finally:
        await db.close()


async def main() -> None:
    configure_logging()
    load_env()
    if not check_env_vars(REQUIRED_ENV_VARS):
        return

    try:
        await _run_agents()
    except GenAPIError as exc:
        logging.error("Ошибка GenAPI: %s", exc)
    except Exception:
        logging.exception("Произошла ошибка во время работы агента.")


if __name__ == "__main__":
    asyncio.run(main())
