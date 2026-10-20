"""Exception types for APKSmith.

One base error, plus specific subclasses. We never let a raw androguard or
subprocess exception escape the ingest layer -- the CLI needs to print one
clean message, not a stack trace.
"""

from __future__ import annotations


class ApkSmithError(Exception):
    """Base class for every error APKSmith raises deliberately."""


class ApkNotFound(ApkSmithError):
    """The APK file does not exist or is not a valid ZIP/APK."""


class DexUnavailable(ApkSmithError):
    """The APK contains no readable DEX, or it is encrypted."""


class JadxUnavailable(ApkSmithError):
    """Decompilation was requested but the jadx binary could not be found."""


class JadxFailed(ApkSmithError):
    """jadx ran but exited with an error."""

    def __init__(self, message: str, returncode: int = -1) -> None:
        super().__init__(message)
        self.returncode = returncode
