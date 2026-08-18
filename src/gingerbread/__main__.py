"""Entry point: ``python -m gingerbread``.

The environment variable is set **before** anything imports pygame.  Otherwise
pygame prints its version banner to stdout, which lands in the middle of
``--check``'s JSON — so upgrading pygame would break a byte-for-byte comparison
for a reason that has nothing to do with the game, and ``--check | jq`` would
simply fail.
"""

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from .app import main                                    # noqa: E402

raise SystemExit(main())
