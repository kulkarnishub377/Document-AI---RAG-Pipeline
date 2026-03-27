# utils/__init__.py
from utils.exceptions import (
    PipelineError,
    DocumentNotFoundError,
    UnsupportedFileTypeError,
    FileTooLargeError,
    OllamaNotReachableError,
    IndexNotFoundError,
    RateLimitExceededError,
    IngestionError,
)

__all__ = [
    "PipelineError",
    "DocumentNotFoundError",
    "UnsupportedFileTypeError",
    "FileTooLargeError",
    "OllamaNotReachableError",
    "IndexNotFoundError",
    "RateLimitExceededError",
    "IngestionError",
]
