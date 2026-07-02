class PKBError(Exception):
    """Base exception for the personal knowledge base."""


class ConfigError(PKBError):
    """Raised when configuration cannot be loaded."""


class CollectionError(PKBError):
    """Raised when data collection fails."""


class ParseError(PKBError):
    """Raised when parsing fails."""


class CheckpointError(PKBError):
    """Raised when checkpoint persistence fails."""
