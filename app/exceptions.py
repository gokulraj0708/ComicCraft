"""Domain-specific exceptions."""


class ComicCraftError(Exception):
    """Base exception for user-safe application failures."""

    status_code = 500


class ConfigurationError(ComicCraftError):
    status_code = 503


class GenerationError(ComicCraftError):
    status_code = 502


class ComicNotFoundError(ComicCraftError):
    status_code = 404
