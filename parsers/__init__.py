"""Parsers for spatial transcriptomics platform formats.

This package contains *optional* Python utilities (pandas/h5py/scipy, etc.) for
converting native platform exports (Xenium, CosMx, MERSCOPE, Visium) into the
standardized structures used by Spatial Explorer.

Important
---------
We keep imports *lazy* so that ``import parsers`` works even when optional
dependencies like ``pandas`` are not installed.

Consumers can import specific parsers directly:

    from parsers.xenium import parse_xenium

or use the universal loader:

    from parsers.universal import load_spatial

T-990
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "parse_cosmx",
    "parse_merscope",
    "parse_visium",
    "parse_visium_hd",
    "parse_xenium",
    "detect_spatial_format",
    "load_spatial",
]


_LAZY_ATTRS = {
    "parse_cosmx": ("parsers.cosmx", "parse_cosmx"),
    "parse_merscope": ("parsers.merscope", "parse_merscope"),
    "parse_visium": ("parsers.visium", "parse_visium"),
    "parse_visium_hd": ("parsers.visium_hd", "parse_visium_hd"),
    "parse_xenium": ("parsers.xenium", "parse_xenium"),
    "detect_spatial_format": ("parsers.universal", "detect_spatial_format"),
    "load_spatial": ("parsers.universal", "load_spatial"),
}


def __getattr__(name: str) -> Any:  # PEP 562
    if name not in _LAZY_ATTRS:
        raise AttributeError(name)
    mod_name, attr = _LAZY_ATTRS[name]
    mod = importlib.import_module(mod_name)
    return getattr(mod, attr)


def __dir__() -> list[str]:
    # Do *not* advertise lazy attributes via dir(). Some tooling (notably
    # unittest discovery) will iterate dir(module) and getattr() each entry,
    # which would defeat lazy imports and re-introduce optional dependency
    # import errors.
    return sorted(set(list(globals().keys())))


def load_tests(loader, tests, pattern):  # pragma: no cover
    """Prevent unittest discovery from importing optional dependencies.

    `unittest` treats packages as potential test containers and will inspect
    attributes on import, which would otherwise trigger our lazy imports.
    This package is *not* a test module, so we return the collected tests
    unchanged.
    """

    return tests
