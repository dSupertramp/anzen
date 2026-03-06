"""
CLI entry-point for Anzen.

Usage:
    anzen monitor              # start dashboard on :8000
    anzen monitor --port 9000  # custom port
    anzen monitor --no-open    # don't auto-open browser
"""

import argparse
import os
import pathlib
import threading
import time
import webbrowser

import uvicorn


def cmd_monitor(args):
    data_dir = pathlib.Path.home() / ".anzen"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "anzen.db"

    os.environ.setdefault("ANZEN_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    os.environ.setdefault("ANZEN_CORS_ORIGINS", '["*"]')

    url = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"

    if not args.no_open:
        def _open():
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  Anzen Monitor → {url}\n")

    uvicorn.run(
        "anzen.server.app:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        prog="anzen",
        description="Anzen — open-source security layer for agentic AI",
    )
    sub = parser.add_subparsers(dest="command")

    mon = sub.add_parser("monitor", help="Launch the Anzen dashboard")
    mon.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    mon.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    mon.add_argument("--no-open", action="store_true", help="Don't open browser automatically")

    args = parser.parse_args()

    if args.command == "monitor":
        cmd_monitor(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
