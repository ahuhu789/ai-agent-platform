import logging
from uuid import uuid4

from shared.logger import setup_logger


def test_child_log_is_emitted_once(capsys):
    parent = logging.getLogger(f"fme.test.{uuid4().hex}")
    child = logging.getLogger(f"{parent.name}.child")
    snapshots = {
        logger: (list(logger.handlers), logger.propagate)
        for logger in (parent, child)
    }

    try:
        setup_logger(parent.name)
        setup_logger(child.name)
        marker = f"log-marker-{uuid4().hex}"

        child.info(marker)

        assert capsys.readouterr().err.count(marker) == 1
    finally:
        for logger, (handlers, propagate) in snapshots.items():
            logger.handlers = handlers
            logger.propagate = propagate
