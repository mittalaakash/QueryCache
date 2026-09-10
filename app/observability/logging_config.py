"""Central logging setup — call once at process start (both the FastAPI app
and CLI scripts use this so log format is consistent everywhere)."""

import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
