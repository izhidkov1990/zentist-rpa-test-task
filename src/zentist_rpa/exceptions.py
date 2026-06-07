class PortalError(Exception):
    """Base exception for portal processing errors."""


class PortalBusinessError(PortalError):
    """A deterministic portal-side business condition, such as a locked account."""


class TransientPortalError(PortalError):
    """A retryable portal condition, such as a dropped session or timeout."""
