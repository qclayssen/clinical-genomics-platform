"""Every pipeline module pins its container by immutable digest (ADR-0009).

A tag like ``fastp:0.23.4`` can be re-pushed; ``@sha256:`` cannot. This guards against a
new or edited module slipping back to a tag-only reference.
"""
import re
from pathlib import Path

MODULES = Path(__file__).resolve().parent.parent / "pipeline" / "modules"
CONTAINER = re.compile(r"^\s*container\s+'([^']+)'", re.MULTILINE)
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def _module_files():
    files = sorted(MODULES.rglob("*.nf"))
    assert files, f"no modules found under {MODULES}"
    return files


def test_every_module_declares_one_container():
    for nf in _module_files():
        found = CONTAINER.findall(nf.read_text())
        assert len(found) == 1, f"{nf.relative_to(MODULES)}: expected 1 container, got {found}"


def test_every_container_is_digest_pinned():
    unpinned = [
        f"{nf.relative_to(MODULES)}: {img}"
        for nf in _module_files()
        for img in CONTAINER.findall(nf.read_text())
        if not DIGEST.search(img)
    ]
    assert not unpinned, "containers not pinned by @sha256 digest:\n" + "\n".join(unpinned)
