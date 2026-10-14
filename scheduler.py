"""Единый планировщик запуска агентов hidden_gems и hidden_actors."""

import asyncio
import datetime
import logging
import os
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from agents.hidden_actors.main import main as run_hidden_actors
from agents.hidden_gems.main import main as run_hidden_gems
from logging_config import configure_logging

DEFAULTS = {
    "GEMS_HOUR": "10",
    "GEMS_MINS": "0",
    "ACTORS_DAYS": "mon,thu",
    "ACTORS_HOUR": "12",
    "ACTORS_MINS": "0",
    "JITTER_SECONDS": "900",
}


def load_env() -> None:
    """Load environment variables from .env when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv()


def _env(name: str) -> str:
    return os.getenv(name, DEFAULTS[name])


def _int_env(name: str) -> int:
    return int(_env(name))


def _minutes_env(name: str) -> str:
    """Минуты публикаций: список через запятую (например, "0,30")."""
    raw = os.getenv(name) or DEFAULTS[name]

    minutes = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if not 0 <= value <= 59:
            raise ValueError(
                f"{name}: минуты должны быть в диапазоне 0..59, получено {value}"
            )
        minutes.append(str(value))

    if not minutes:
        raise ValueError(f"{name}: не задано ни одной минуты")

    return ",".join(minutes)


def _target_timezone() -> datetime.tzinfo:
    """Таймзона расписания: локальное серверное время."""
    return datetime.datetime.now().astimezone().tzinfo or datetime.timezone.utc


async def start_scheduler() -> None:
    """Запустить планировщик с задачами для обоих агентов."""
    configure_logging()
    load_env()

    gems_hour = _int_env("GEMS_HOUR")
    gems_minute = _minutes_env("GEMS_MINS")
    actors_days = _env("ACTORS_DAYS")
    actors_hour = _int_env("ACTORS_HOUR")
    actors_minute = _minutes_env("ACTORS_MINS")
    jitter_seconds = _int_env("JITTER_SECONDS")
    timezone = _target_timezone()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_hidden_gems,
        "cron",
        id="hidden_gems",
        name="hidden_gems",
        hour=gems_hour,
        minute=gems_minute,
        timezone=timezone,
        jitter=jitter_seconds,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_hidden_actors,
        "cron",
        id="hidden_actors",
        name="hidden_actors",
        day_of_week=actors_days,
        hour=actors_hour,
        minute=actors_minute,
        timezone=timezone,
        jitter=jitter_seconds,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    logging.info("Планировщик запущен. Время указано в %s.", timezone)
    logging.info(
        "hidden_gems: ежедневно в %02d:%s.",
        gems_hour,
        gems_minute,
    )
    logging.info(
        "hidden_actors: по %s в %02d:%s.",
        actors_days,
        actors_hour,
        actors_minute,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        scheduler.shutdown()
        logging.info("Планировщик остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(start_scheduler())
    except KeyboardInterrupt:
        logging.info("Работа планировщика прервана.")
    finally:
        logging.shutdown()
