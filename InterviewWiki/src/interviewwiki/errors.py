class InterviewWikiError(RuntimeError):
    """Base error for user-actionable InterviewWiki failures."""


class ConfigurationError(InterviewWikiError):
    """Raised when project configuration is missing or unsafe."""


class ValidationFailure(InterviewWikiError):
    """Raised when a strict validation gate does not pass."""
