"""Read Codex rollouts without changing their stored compression or identity."""

from pathlib import Path


def resolve_rollout(path):
    path = Path(path)
    compressed = Path(str(path) + '.zst')
    if not path.exists() and path.name.endswith('.jsonl') and compressed.exists():
        return compressed
    return path


def open_rollout(path):
    path = Path(path)
    if path.name.endswith('.jsonl.zst'):
        try:
            from compression import zstd
        except ImportError as exc:
            raise OSError('Compressed Codex rollouts require Python 3.14 or later') from exc
        return zstd.open(path, 'rb')
    return path.open('rb')
