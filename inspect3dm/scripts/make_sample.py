"""Regenerate samples/sample.3dm (synthetic, created with rhino3dm)."""

from pathlib import Path

from make_fixtures import build_sample

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "samples" / "sample.3dm"
    print(build_sample(out))
