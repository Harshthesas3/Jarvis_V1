"""JARVIS startup subsystem — concurrent pre-warming and readiness tracking.

Usage
-----
::

    from jarvis.startup import get_startup_manager

    mgr = get_startup_manager()
    mgr.prewarm_all(cfg)          # blocks until all tasks finish (or timeout)
    mgr.is_ready("whisper")       # True once whisper prewarm succeeded
    mgr.get_timeline()            # dict of subsystem → ms
"""

from jarvis.startup.manager import StartupManager, get_startup_manager

__all__ = ["StartupManager", "get_startup_manager"]
