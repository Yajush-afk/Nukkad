import argparse
from dataclasses import replace

import uvicorn

from nukkad.app import create_app
from nukkad.config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description="Local neighbourhood discovery")
    parser.add_argument("command", choices=["serve", "benchmark"], nargs="?", default="serve")
    parser.add_argument("--model")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    config = Config()
    if args.model:
        config = replace(config, model=args.model)
    if args.command == "benchmark":
        from nukkad.benchmark import benchmark

        benchmark(config)
    else:
        uvicorn.run(create_app(config), host="127.0.0.1", port=args.port, access_log=False)
