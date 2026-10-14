"""Загрузка промптов из внешних .md файлов.

Промпты читаются из каталога PROMPTS_DIR (по умолчанию "prompts") при каждом
обращении, поэтому изменения в файлах подхватываются без пересборки образа.
Если файл отсутствует или пуст — используется значение по умолчанию из кода.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts"))


def load_prompt(name: str, default: str) -> str:
    """Прочитать промпт из PROMPTS_DIR/<name>.md, иначе вернуть default."""
    path = PROMPTS_DIR / f"{name}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return default

    if not text.strip():
        logger.warning("Промпт %s пуст, используется значение по умолчанию.", path)
        return default

    return text
