"""Universal spatial data loader.

This module provides a small convenience wrapper that *auto-detects* the input
format and dispatches to the appropriate parser.

Supported inputs
----------------
- Native platform directories:
  - CosMx (NanoString/Bruker) -> ``parse_cosmx``
  - MERSCOPE (Vizgen MERFISH) -> ``parse_merscope``
  - Visium (10x Genomics, standard) -> ``parse_visium``
  - Visium HD (10x Genomics Space Ranger binned outputs) -> ``parse_visium_hd``
  - Xenium (10x Genomics) -> ``parse_xenium``

- Standard tabular cell-level files:
  - CSV/TSV (optionally gzipped) with required columns: cell_id, x, y
  - Optional: cell_type
  - Remaining columns are interpreted as gene expression values.

The return value matches the project-wide contract used by the individual
parsers:

    {
        'platform': str,
        'transcript_data': DataFrame,   # columns: x, y, gene, cell_id
        'cell_metadata': DataFrame,     # columns: cell_id, x, y, cell_type
        'expression_matrix': DataFrame, # index: cell_id, columns: genes
        'metadata': dict,
    }

Notes on imports
----------------
This repository stores Spatial Explorer under ``projects/spatial-explorer/``
(hyphenated), which is not importable as a standard Python package.

To keep this module usable from tests and scripts that load it by file path, we
load sibling parser modules dynamically rather than relying on relative imports.

T-992
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


SpatialPlatform = Literal["cosmx", "merscope", "visium", "visium_hd", "xenium", "tabular"]


@dataclass(frozen=True)
class DetectionResult:
    platform: SpatialPlatform
    reason: str


_TRANSCRIPT_COLS = ["x", "y", "gene", "cell_id"]
_CELL_COLS = ["cell_id", "x", "y", "cell_type"]


def _load_sibling(module_filename: str, module_name: str):
    base = Path(__file__).resolve().parent
    path = base / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:  # pragma: no cover
        raise ImportError(f"Failed to load module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    # Some libraries expect the module to exist in sys.modules during execution.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


@lru_cache(maxsize=None)
def _sibling(mod_filename: str, module_name: str):
    return _load_sibling(mod_filename, module_name)


def _get_parser(platform: SpatialPlatform):
    if platform == "cosmx":
        return _sibling("cosmx.py", "spatial_explorer_cosmx").parse_cosmx
    if platform == "merscope":
        return _sibling("merscope.py", "spatial_explorer_merscope").parse_merscope
    if platform == "visium":
        return _sibling("visium.py", "spatial_explorer_visium").parse_visium
    if platform == "visium_hd":
        return _sibling("visium_hd.py", "spatial_explorer_visium_hd").parse_visium_hd
    if platform == "xenium":
        return _sibling("xenium.py", "spatial_explorer_xenium").parse_xenium

    raise ValueError(f"Unsupported platform: {platform}")


def load_spatial(input_path: str | Path) -> dict[str, Any]:
    """Load spatial data from a directory or a file."""

    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"Input path does not exist: {p}")

    det = detect_spatial_format(p)

    if det.platform == "tabular":
        out = _parse_tabular_cells(p)
    else:
        out = _get_parser(det.platform)(p)

    out.setdefault("metadata", {})
    out["metadata"].setdefault(
        "detection",
        {"platform": det.platform, "reason": det.reason, "input_path": str(p)},
    )
    return out


def detect_spatial_format(input_path: str | Path) -> DetectionResult:
    """Detect the most likely spatial platform/format for the given path."""

    p = Path(input_path)
    if p.is_file():
        if _is_tabular_file(p):
            return DetectionResult(platform="tabular", reason=f"file suffix={''.join(p.suffixes).lower()}")
        raise ValueError(
            "Input is a file, but not a supported tabular format. "
            "Expected .csv/.tsv/.txt (optionally .gz). "
            f"Got: {p.name}"
        )

    if not p.is_dir():
        raise ValueError(f"Input path is neither a file nor a directory: {p}")

    names = {c.name.lower() for c in p.iterdir()}

    # MERSCOPE strong signals.
    #
    # Vizgen exports vary: sometimes the user points us at the folder that
    # directly contains tables, sometimes a folder that contains
    # analysis_outputs/, and sometimes a higher-level folder containing
    # region_* subfolders.
    merscope_signature = {
        "detected_transcripts.csv",
        "detected_transcripts.parquet",
        "cell_by_gene.csv",
        "cell_by_gene.parquet",
        "entity_by_gene.csv",
        "entity_by_gene.parquet",
    }

    def _dirnames(d: Path) -> set[str]:
        try:
            return {c.name.lower() for c in d.iterdir()}
        except Exception:
            return set()

    def _merscope_in_dir(d: Path, label: str) -> DetectionResult | None:
        dn = _dirnames(d)
        if merscope_signature & dn:
            return DetectionResult(platform="merscope", reason=f"matched MERSCOPE signature in {label}")

        if any("detected_transcripts" in n for n in dn) and any(
            "cell_by_gene" in n or "entity_by_gene" in n for n in dn
        ):
            return DetectionResult(
                platform="merscope",
                reason=f"found detected_transcripts* and cell_by_gene*/entity_by_gene* in {label}",
            )

        # Transcript-only or expression-only drops are common; treat as MERSCOPE.
        if any("detected_transcripts" in n for n in dn) or any(
            "cell_by_gene" in n or "entity_by_gene" in n for n in dn
        ):
            if any(n.endswith((".csv", ".csv.gz", ".parquet")) for n in dn):
                return DetectionResult(platform="merscope", reason=f"weak MERSCOPE match in {label}")

        return None

    # Prefer direct hits at the provided directory, then analysis_outputs,
    # then immediate children (e.g. region_0/).
    to_check: list[tuple[Path, str]] = [(p, "root")]
    if (p / "analysis_outputs").exists():
        to_check.append((p / "analysis_outputs", "analysis_outputs"))

    for child in sorted(p.iterdir()):
        if not child.is_dir():
            continue
        to_check.append((child, f"child:{child.name}"))
        if (child / "analysis_outputs").exists():
            to_check.append((child / "analysis_outputs", f"child:{child.name}/analysis_outputs"))

    for d, label in to_check:
        res = _merscope_in_dir(d, label)
        if res is not None:
            return res

    # Visium HD signals.
    if _looks_like_visium_hd_root(p, names):
        return DetectionResult(platform="visium_hd", reason="found Space Ranger binned_outputs/")

    # Visium (standard) signals.
    if _looks_like_visium_root(p, names):
        return DetectionResult(platform="visium", reason="found spatial/tissue_positions* and feature_bc_matrix")

    # Xenium strong signals.
    if {
        "transcripts.parquet",
        "cells.parquet",
        "cell_feature_matrix.h5",
        "experiment.xenium",
    } & names:
        return DetectionResult(platform="xenium", reason="matched Xenium signature filename")

    if any(n.startswith("transcripts") for n in names) and any(n.startswith("cells") for n in names):
        return DetectionResult(platform="xenium", reason="found transcripts* and cells* files")

    if "cell_feature_matrix" in names:
        return DetectionResult(platform="xenium", reason="found cell_feature_matrix directory")

    # CosMx signals.
    if {"tx_file.csv", "cell_metadata.csv", "exprmat_file.csv"} & names:
        return DetectionResult(platform="cosmx", reason="matched CosMx signature filename")

    if any("tx_" in n or "transcript" in n for n in names) and any(
        "cell_metadata" in n or "cellmeta" in n for n in names
    ):
        return DetectionResult(platform="cosmx", reason="found tx/transcript and cell metadata files")

    # Convenience: if directory contains exactly one tabular file, treat it as a drop.
    tabulars = [c for c in p.iterdir() if c.is_file() and _is_tabular_file(c)]
    if len(tabulars) == 1:
        return DetectionResult(platform="tabular", reason=f"directory contains single tabular file: {tabulars[0].name}")

    raise ValueError(
        "Could not determine spatial format for directory. "
        "Expected a CosMx, MERSCOPE, Visium/Visium HD, or Xenium output directory, or a CSV/TSV file. "
        f"Directory: {p}"
    )


def _looks_like_visium_root(p: Path, names: set[str]) -> bool:
    if "spatial" not in names:
        return False

    if not (
        "filtered_feature_bc_matrix" in names
        or "filtered_feature_bc_matrix.h5" in names
        or "raw_feature_bc_matrix" in names
        or "raw_feature_bc_matrix.h5" in names
    ):
        return False

    try:
        spatial_names = {c.name.lower() for c in (p / "spatial").iterdir()}
    except Exception:
        spatial_names = set()

    return bool({"tissue_positions.csv", "tissue_positions_list.csv", "tissue_positions.parquet", "tissue_positions_list.parquet"} & spatial_names)


def _looks_like_visium_hd_root(p: Path, names: set[str]) -> bool:
    # Most Space Ranger HD outputs contain binned_outputs/<bin>/...
    if "binned_outputs" in names:
        b = p / "binned_outputs"
        try:
            for d in b.iterdir():
                if not d.is_dir():
                    continue
                d_names = {c.name.lower() for c in d.iterdir()}
                if _looks_like_visium_root(d, d_names) or "spatial" in d_names:
                    return True
        except Exception:
            return False

    # If the user points directly at a bin directory, detect it heuristically.
    if "spatial" in names and (
        "filtered_feature_bc_matrix" in names
        or "filtered_feature_bc_matrix.h5" in names
        or "raw_feature_bc_matrix" in names
        or "raw_feature_bc_matrix.h5" in names
    ):
        nm = p.name.lower()
        if nm.startswith("square_") and "um" in nm:
            return True
        if p.parent.name.lower() == "binned_outputs":
            return True

    return False


def _is_tabular_file(p: Path) -> bool:
    suf = "".join(p.suffixes).lower()
    return suf in {".csv", ".tsv", ".txt", ".csv.gz", ".tsv.gz", ".txt.gz"}


def _parse_tabular_cells(path: Path) -> dict[str, Any]:
    """Parse a standard cell-level CSV/TSV file."""

    try:
        import pandas as pd  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "Tabular parsing requires the optional dependency 'pandas'. "
            f"Install pandas or provide a native platform directory instead. ({e})"
        ) from e

    if not path.is_file():
        raise ValueError(f"Tabular input must be a file: {path}")

    try:
        df = pd.read_csv(path, sep=None, engine="python")
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Failed reading tabular cells file {path}: {e}") from e

    df.columns = [str(c).strip() for c in df.columns]

    colmap: dict[str, str] = {}
    for c in df.columns:
        colmap.setdefault(str(c).strip().lower(), c)

    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell", "barcode", "id"])
    x_col = _first_present(colmap, ["x", "x_coord", "xcoord", "x_centroid", "centerx", "centroid_x"])
    y_col = _first_present(colmap, ["y", "y_coord", "ycoord", "y_centroid", "centery", "centroid_y"])
    type_col = _first_present(colmap, ["cell_type", "celltype", "type", "annotation", "cluster", "label"])

    missing = [name for name, col in [("cell_id", cell_col), ("x", x_col), ("y", y_col)] if col is None]
    if missing:
        raise ValueError(
            f"Tabular cells file missing required columns {missing}. "
            f"Found columns: {list(df.columns)} (file: {path})"
        )

    cell_metadata = pd.DataFrame(
        {
            "cell_id": df[cell_col].astype("string"),
            "x": pd.to_numeric(df[x_col], errors="coerce"),
            "y": pd.to_numeric(df[y_col], errors="coerce"),
            "cell_type": df[type_col].astype("string") if type_col is not None else pd.Series([pd.NA] * len(df), dtype="string"),
        }
    )

    known_cols = {cell_col, x_col, y_col}
    if type_col is not None:
        known_cols.add(type_col)

    gene_cols = [c for c in df.columns if c not in known_cols]

    if gene_cols:
        expr = df[gene_cols].copy()
        expr.index = cell_metadata["cell_id"].astype("string")
        expr.index.name = "cell_id"
        expr = expr.apply(pd.to_numeric, errors="coerce").fillna(0)
    else:
        expr = pd.DataFrame(index=pd.Index(cell_metadata["cell_id"].astype("string"), name="cell_id"))

    transcript_data = pd.DataFrame({c: pd.Series(dtype="object") for c in _TRANSCRIPT_COLS})

    if cell_metadata[["x", "y"]].isna().any().any():
        n = int(cell_metadata[["x", "y"]].isna().any(axis=1).sum())
        logger.warning("Tabular: %s rows have NaN x/y coordinates (%s)", n, path.name)

    return {
        "platform": "tabular",
        "transcript_data": transcript_data,
        "cell_metadata": cell_metadata[_CELL_COLS],
        "expression_matrix": expr,
        "metadata": {"input_file": str(path)},
    }


def _first_present(colmap: dict[str, str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colmap:
            return colmap[c]
    return None
