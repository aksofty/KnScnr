import logging
import os


def configure_logging() -> None:
    """Configure application-wide logging to append to a log file and stdout."""
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(os.getenv("LOG_FILE", "app.log"), encoding="utf-8")
    file_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [file_handler]
    if os.getenv("LOG_STDOUT", "1") == "1":
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        handlers=handlers,
    )
