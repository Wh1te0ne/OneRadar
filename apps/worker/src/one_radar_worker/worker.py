from __future__ import annotations

import argparse
import logging
from time import sleep

from sqlalchemy.exc import OperationalError, ProgrammingError

from .processor import run_task
from .settings import Settings
from .storage import build_engine, claim_next_task


LOGGER = logging.getLogger('one_radar_worker')


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )


def process_available_tasks(settings: Settings) -> int:
    engine = build_engine(settings.database_url)
    processed = 0
    while True:
        task = claim_next_task(engine)
        if task is None:
            break
        outcome = run_task(engine, task)
        processed += 1
        LOGGER.info(
            'processed task',
            extra={
                'task_id': str(task['id']),
                'item_id': str(task['content_item_id']),
                'task_type': task['task_type'],
                'status': outcome.status.value,
                'outcome_message': outcome.message,
            },
        )
    return processed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='OneRadar worker skeleton')
    parser.add_argument('--once', action='store_true', help='Process available tasks and exit')
    return parser


def main() -> int:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    parser = build_parser()
    args = parser.parse_args()

    if args.once:
        processed = process_available_tasks(settings)
        LOGGER.info('worker cycle finished', extra={'processed': processed})
        return 0

    while True:
        try:
            processed = process_available_tasks(settings)
            LOGGER.info('worker cycle finished', extra={'processed': processed})
        except (OperationalError, ProgrammingError) as exc:
            LOGGER.warning('worker backing services not ready: %s', exc)
        sleep(5)


if __name__ == '__main__':
    raise SystemExit(main())
