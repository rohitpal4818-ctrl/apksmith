"""
Logging control.

androguard uses `loguru` and defaults to DEBUG for its internal XML and DEX
parsers. On a large APK that produces tens of thousands of lines and will
swamp any real output, so we silence it by default.

Set ``APKSMITH_DEBUG=1`` to let androguard speak for itself when you actually
need to debug a parsing problem.
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure_logging(verbose: bool = False) -> None:
    """Silence androguard unless the caller asked for detail.

    Call this before touching androguard. It is idempotent.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    env_debug = os.environ.get("APKSMITH_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if verbose or env_debug:
        # Let loguru through, but stop it being DEBUG about every tag.
        try:
            from loguru import logger

            logger.remove()
            logger.add(
                sys_stderr(),
                level="INFO",
                format="<level>{level: <7}</level> | {message}",
            )
        except Exception:
            pass
    else:
        try:
            from loguru import logger

            logger.remove()
        except Exception:
            pass

    # androguard also touches the stdlib logger in places.
    logging.getLogger("androguard").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    _CONFIGURED = True


def sys_stderr():
    """Late-bound stderr sink so we don't bind it at import time."""
    import sys

    return sys.stderr