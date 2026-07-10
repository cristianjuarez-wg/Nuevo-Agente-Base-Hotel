from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from openai import APIError, RateLimitError, APIConnectionError
from app.core.observability.logging_config import get_logger
from app.config import settings
import logging

logger = get_logger(__name__)

# Configuración de reintentos para OpenAI
openai_retry = retry(
    stop=stop_after_attempt(settings.OPENAI_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((APIError, RateLimitError, APIConnectionError)),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)

# Configuración para operaciones de base de datos
db_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=2, max=6),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)

# Configuración para operaciones de ChromaDB
vector_store_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=1, max=5),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
