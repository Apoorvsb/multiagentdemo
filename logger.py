import logging
import sys
import os

os.makedirs("logs", exist_ok=True)


def _setup_logger():
    logger = logging.getLogger("multi_agent_app")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)-8s | "
            "request_id=%(request_id)s | "
            "agent=%(agent_name)s | "
            "node=%(node_name)s | "
            "%(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(file_handler)

    return logger


_logger = _setup_logger()


def get_log(request_id: str, agent_name: str = "-", node_name: str = "-"):
    return logging.LoggerAdapter(_logger, {
        "request_id": request_id,
        "agent_name": agent_name,
        "node_name": node_name,
    })