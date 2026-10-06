from __future__ import annotations

from .providers.base import ProviderError


class InputBudgetError(ProviderError):
    def __init__(self, message: str):
        super().__init__(message, code="INPUT_TOO_LARGE", dispatch="not_sent")


def safe_failure(error: BaseException) -> dict:
    from .coaching import CoachingValidationError
    from .localization import LocalizationValidationError

    if isinstance(error, LocalizationValidationError):
        return {
            "code": "VALIDATION_FAILED",
            "stage": "localization",
            "reason": error.reason,
            "ordinal": error.ordinal,
            "message": "A question translation needs correction. Retry preparation or use native fixed questions. Saved work is preserved.",
            "dispatch_state": "received",
        }

    if isinstance(error, CoachingValidationError):
        return {
            "code": "VALIDATION_FAILED",
            "reason": error.code,
            "clause": error.clause,
            "message": "The example needs evidence or wording correction. Saved work is preserved.",
            "dispatch_state": "received",
        }
    if isinstance(error, TimeoutError):
        return ProviderError(
            "Task timed out. Saved results remain available; resume explicitly.",
            code="TIMEOUT",
            dispatch="unknown",
        ).diagnostic()
    if isinstance(error, ProviderError):
        return error.diagnostic()
    if isinstance(error, (KeyboardInterrupt, SystemExit)) or error.__class__.__name__ == "CancelledError":
        return {
            "code": "INTERRUPTED",
            "message": "Work interrupted. Resume explicitly from saved progress.",
            "dispatch_state": "unknown",
        }
    # SDK exception strings can contain prompts, headers and private paths.
    return {
        "code": "VALIDATION_FAILED",
        "message": "The task could not produce validated output. Saved work is preserved.",
        "dispatch_state": "unknown",
    }
