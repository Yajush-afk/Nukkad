import argparse
from dataclasses import replace
from pathlib import Path

import uvicorn

from nukkad.app import create_app
from nukkad.config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description="Local neighbourhood discovery")
    parser.add_argument(
        "command", choices=["serve", "benchmark", "backup", "restore"], nargs="?", default="serve"
    )
    parser.add_argument("--model")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    config = Config()
    if args.model:
        config = replace(config, model=args.model)
    if args.command == "benchmark":
        from nukkad.benchmark import benchmark

        benchmark(config)
    elif args.command == "backup":
        from nukkad.backups import backup

        print(backup(config))
    elif args.command == "restore":
        from nukkad.backups import restore

        if not args.archive or not args.destination:
            parser.error("restore requires --archive and --destination (a new directory)")
        print(restore(args.archive, args.destination))
    else:
        uvicorn.run(create_app(config), host="127.0.0.1", port=args.port, access_log=False)
