from enum import Enum
from datetime import datetime, timedelta
from typing import Callable, Any
from app.core.logging_config import get_logger
from app.config import settings

logger = get_logger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Too many failures, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """Circuit breaker para proteger servicios externos"""
    
    def __init__(
        self,
        failure_threshold: int = None,
        timeout_seconds: int = None,
        expected_exception: Exception = Exception
    ):
        self.failure_threshold = failure_threshold or settings.CIRCUIT_BREAKER_THRESHOLD
        self.timeout_seconds = timeout_seconds or settings.CIRCUIT_BREAKER_TIMEOUT
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        
        logger.info("Circuit breaker initialized",
                   failure_threshold=self.failure_threshold,
                   timeout_seconds=self.timeout_seconds)
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Ejecuta función con circuit breaker"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("circuit_breaker_half_open", func=func.__name__)
            else:
                logger.warning("circuit_breaker_open", 
                             func=func.__name__,
                             failure_count=self.failure_count)
                raise Exception(f"Circuit breaker is OPEN for {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            self._on_success(func.__name__)
            return result
        
        except self.expected_exception as e:
            self._on_failure(func.__name__)
            raise e
    
    async def acall(self, func: Callable, *args, **kwargs) -> Any:
        """Versión asíncrona del circuit breaker"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info("circuit_breaker_half_open", func=func.__name__)
            else:
                logger.warning("circuit_breaker_open", 
                             func=func.__name__,
                             failure_count=self.failure_count)
                raise Exception(f"Circuit breaker is OPEN for {func.__name__}")
        
        try:
            if hasattr(func, '__call__'):
                result = await func(*args, **kwargs)
            else:
                result = await func
            self._on_success(func.__name__ if hasattr(func, '__name__') else 'async_func')
            return result
        
        except self.expected_exception as e:
            self._on_failure(func.__name__ if hasattr(func, '__name__') else 'async_func')
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Verifica si debería intentar resetear el circuit breaker"""
        return (
            self.last_failure_time and
            datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout_seconds)
        )
    
    def _on_success(self, func_name: str):
        """Maneja operación exitosa"""
        if self.failure_count > 0 or self.state != CircuitState.CLOSED:
            logger.info("circuit_breaker_success",
                       func=func_name,
                       previous_failures=self.failure_count)
        
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info("circuit_breaker_closed", func=func_name)
    
    def _on_failure(self, func_name: str):
        """Maneja falla"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        logger.warning("circuit_breaker_failure",
                      func=func_name,
                      failure_count=self.failure_count,
                      threshold=self.failure_threshold)
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error("circuit_breaker_opened",
                        func=func_name,
                        failure_count=self.failure_count,
                        timeout_seconds=self.timeout_seconds)
    
    def get_state(self) -> dict:
        """Obtiene estado actual del circuit breaker"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "timeout_seconds": self.timeout_seconds
        }
    
    def reset(self):
        """Resetea manualmente el circuit breaker"""
        logger.info("circuit_breaker_manual_reset",
                   previous_state=self.state.value,
                   previous_failures=self.failure_count)
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

# Instancias globales para diferentes servicios
from openai import APIError, RateLimitError, APIConnectionError, APITimeoutError

# Solo errores REALES de la API de OpenAI abren el circuito. Antes incluía Exception
# genérica, lo que hacía que un bug de código (TypeError, KeyError) abriera el circuito
# de OpenAI por error y silenciara el servicio 60s. RateLimitError/APITimeoutError son
# subclases de APIError, pero las listamos explícitamente por claridad.
openai_circuit_breaker = CircuitBreaker(
    failure_threshold=settings.CIRCUIT_BREAKER_THRESHOLD,
    timeout_seconds=settings.CIRCUIT_BREAKER_TIMEOUT,
    expected_exception=(APIError, RateLimitError, APIConnectionError, APITimeoutError)
)

vector_store_circuit_breaker = CircuitBreaker(
    failure_threshold=3,
    timeout_seconds=30,
    expected_exception=Exception
)
