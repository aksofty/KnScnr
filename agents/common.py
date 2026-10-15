"""Общие утилиты агентов: загрузка env и проверка переменных окружения."""

import logging
import os


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
