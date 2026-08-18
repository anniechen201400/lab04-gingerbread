"""Build the browser version with pygbag.

The web runtime has no system fonts and no src/ layout, so this script
assembles a flat folder that pygbag can compile to WebAssembly:

    web/
      main.py            async entry point
      gingerbread/       a copy of the package
      assets/            the subset CJK font

Run:  python build_web.py          then open build/web/index.html
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
WEB = ROOT / "web"

MAIN = '''"""Browser entry point (pygbag compiles this to WebAssembly)."""

import asyncio
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from gingerbread.app.game import Game


async def main() -> None:
    await Game(seed=42).run()


asyncio.run(main())
'''


def stage() -> None:
    if WEB.exists():
        shutil.rmtree(WEB)
    WEB.mkdir()
    shutil.copytree(ROOT / "src" / "gingerbread", WEB / "gingerbread",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "assets", WEB / "assets")
    (WEB / "main.py").write_text(MAIN, encoding="utf-8")
    print(f"staged -> {WEB}")


def build() -> int:
    stage()
    cmd = [sys.executable, "-m", "pygbag", "--build", "--ume_block", "0",
           "--title", "糖果屋之後", str(WEB)]
    print("running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(build())
