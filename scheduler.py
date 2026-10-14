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

JITTER_SECONDS = 3600

DEFAULTS = {
    "TZ_OFFSET": "0",
    "GEMS_HOUR": "10",
    "GEMS_MINUTE": "0",
    "ACTORS_DAYS": "mon,thu",
    "ACTORS_HOUR": "12",
    "ACTORS_MINUTE": "0",
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


def _target_timezone() -> datetime.timezone:
    """Таймзона расписания: серверное смещение плюс TZ_OFFSET (в часах)."""
    server_offset = datetime.datetime.now().astimezone().utcoffset()
    if server_offset is None:
        server_offset = datetime.timedelta(0)
    shift = datetime.timedelta(hours=float(_env("TZ_OFFSET")))
    return datetime.timezone(server_offset + shift)


async def start_scheduler() -> None:
    """Запустить планировщик с задачами для обоих агентов."""
    configure_logging()
    load_env()

    gems_hour = _int_env("GEMS_HOUR")
    gems_minute = _int_env("GEMS_MINUTE")
    actors_days = _env("ACTORS_DAYS")
    actors_hour = _int_env("ACTORS_HOUR")
    actors_minute = _int_env("ACTORS_MINUTE")
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
        jitter=JITTER_SECONDS,
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
        jitter=JITTER_SECONDS,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    logging.info("Планировщик запущен. Время указано в %s.", timezone)
    logging.info(
        "hidden_gems: ежедневно в %02d:%02d.",
        gems_hour,
        gems_minute,
    )
    logging.info(
        "hidden_actors: по %s в %02d:%02d.",
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
