"""Pytest bootstrap: put the repo root on sys.path.

Tests import first-party packages by their real names (``lambdas.shared``,
``demo.intents``, ``agent.*``). Without this, a bare ``pytest`` from a clean
clone dies during collection with ``ModuleNotFoundError: No module named
'lambdas'`` — CI only worked because the workflow exports PYTHONPATH itself
(.github/workflows/pipeline-ci.yml). Keeping it here means the documented
``pytest`` in CLAUDE.md works with no environment setup.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
