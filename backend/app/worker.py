"""Standalone scheduler process: `python -m app.worker` (set SCHEDULER_ENABLED=false on the API containers)."""
import logging
import time
from app.core.config import settings
from app.scheduler import run_once

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    logging.getLogger("app.worker").info("Worker started; interval %ss", settings.scheduler_interval_seconds)
    while True:
        run_once()
        time.sleep(settings.scheduler_interval_seconds)
