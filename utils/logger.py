import logging


def setup_logger(name: str = "swap-logger") -> logging.Logger:
    logger_ = logging.getLogger(name)
    logger_.setLevel(logging.INFO)

    if not logger_.handlers:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        logger_.addHandler(console_handler)
    logger_.propagate = False
    return logger_


logger = setup_logger()
