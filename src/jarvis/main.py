"""JARVIS — AI Operating System for Windows. Main entry point.

Usage:
    python -m jarvis.main
    python -m jarvis.main --headless
    python -m jarvis.main --config custom_config.json
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _ensure_sys_path() -> None:
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = os.path.dirname(src_dir)
    for d in (src_dir, root_dir):
        if d not in sys.path:
            sys.path.insert(0, d)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="JARVIS — AI Operating System for Windows")
    p.add_argument("--headless", action="store_true", help="Text-only mode")
    p.add_argument("--config", type=str, default=None, help="Config path")
    p.add_argument("--version", action="version", version="JARVIS 3.0.0")
    p.add_argument("--health", action="store_true", help="Health check")
    p.add_argument("--api", action="store_true", help="Start in REST API server mode")
    p.add_argument("--port", type=int, default=8000, help="Port for the API server (default: 8000)")
    return p.parse_args()


def main() -> None:
    _ensure_sys_path()
    args = parse_args()

    from jarvis.app import JarvisApplication
    from jarvis.execution.adapter import set_executor_context
    from memory_v2 import get_memory

    app = JarvisApplication(config_path=args.config)

    def _load_apps() -> list:
        import json
        for enc in ("utf-16", "utf-8-sig", "utf-8"):
            try:
                with open("apps.json", "r", encoding=enc) as f:
                    return json.load(f)
            except Exception:
                continue
        return []

    set_executor_context({
        "speak": lambda t: logging.getLogger("jarvis").info("SAY: %s", t),
        "apps": _load_apps(),
        "chat": app.chat_with_llm,
        "memory": get_memory(),
        "settings": None,
    })

    if args.api:
        app.run_api_server(port=args.port)
        return

    if args.health:
        for name, s in app.health_check().items():
            print(f"  {name}: {'OK' if s.healthy else 'FAIL'}")
        return

    if args.headless:
        app.initialize()
        print("\nJARVIS headless mode. Type 'exit' to quit.\n")
        while True:
            try:
                user = input("You: ").strip()
                if not user:
                    continue
                if user.lower() in ("exit", "quit"):
                    break
                from jarvis.execution.adapter import quick_plan, execute_via_engine
                plan = quick_plan(user)
                result = execute_via_engine(app.engine, plan, user) if plan else app.chat_with_llm(user)
                print(f"JARVIS: {result}")
            except KeyboardInterrupt:
                break
        app.shutdown()
    else:
        app.run()


if __name__ == "__main__":
    main()
