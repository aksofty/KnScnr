import logging


def configure_logging() -> None:
    """Configure application-wide logging to append to app.log."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename="app.log",
        filemode="a",
    )
