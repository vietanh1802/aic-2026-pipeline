from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import argparse
import json


def _json_default(value) :
    if (isinstance(value, Path)) :
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _command_validate(args : argparse.Namespace) -> int :
    from .artifacts import validate_release

    manifest = validate_release(
        Path(args.release),
        verify_hashes = not args.skip_hashes,
    )
    print(json.dumps(asdict(manifest), ensure_ascii = False, indent = 2, default = _json_default))
    return 0


def _command_search(args : argparse.Namespace) -> int :
    from .config import ProductionConfig, RuntimeConfig
    from .engine import ASRRetrievalEngine

    runtime = RuntimeConfig(
        e5_device = args.device,
        load_reranker = not args.no_reranker,
        serialize_gpu_requests = True,
        default_top_k = args.top_k,
        default_windows_per_hit = args.windows_per_hit,
    )
    config = ProductionConfig(runtime = runtime)
    engine = ASRRetrievalEngine.from_artifacts(
        Path(args.release),
        config = config,
        warmup = not args.no_warmup,
    )
    try :
        result = engine.search(
            args.query,
            top_k = args.top_k,
            first_stage_only = args.first_stage_only or args.no_reranker,
            windows_per_hit = args.windows_per_hit,
        )
        print(json.dumps(asdict(result), ensure_ascii = False, indent = 2, default = _json_default))
    finally :
        engine.close()
    return 0


def build_parser() -> argparse.ArgumentParser :
    parser = argparse.ArgumentParser(
        prog = "asr-retrieval",
        description = "Standalone ASR transcript retrieval system",
    )
    subparsers = parser.add_subparsers(dest = "command", required = True)

    validate_parser = subparsers.add_parser(
        "validate",
        help = "Validate a searchable corpus package",
    )
    validate_parser.add_argument("--release", required = True)
    validate_parser.add_argument("--skip-hashes", action = "store_true")
    validate_parser.set_defaults(handler = _command_validate)

    search_parser = subparsers.add_parser(
        "search",
        help = "Search a prepared ASR retrieval corpus",
    )
    search_parser.add_argument("--release", required = True)
    search_parser.add_argument("--query", required = True)
    search_parser.add_argument("--top-k", type = int, default = 50)
    search_parser.add_argument("--windows-per-hit", type = int, default = 3)
    search_parser.add_argument("--device", choices = ["cuda", "cpu"], default = "cuda")
    search_parser.add_argument("--first-stage-only", action = "store_true")
    search_parser.add_argument("--no-reranker", action = "store_true")
    search_parser.add_argument("--no-warmup", action = "store_true")
    search_parser.set_defaults(handler = _command_search)

    return parser


def main(argv : list[str] | None = None) -> int :
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if (__name__ == "__main__") :
    raise SystemExit(main())
