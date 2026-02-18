"""MERSCOPE (Vizgen MERFISH) native output parser.

This module implements a lightweight, defensive parser for typical Vizgen
MERSCOPE *native* outputs / post-processing exports.

Common file names (may vary by software version and processing options):

- Detected transcripts (spot table):
  - ``detected_transcripts.csv`` (sometimes parquet in newer versions)
  - Columns documented by Vizgen include:
      - ``global_x``, ``global_y`` (microns)
      - ``gene``
      - Optional segmentation assignment column ``EntityID`` (cell id) where
        -1 indicates unassigned.

- Cell metadata:
  - ``cell_metadata.csv`` (derived by Vizgen post-processing tool) or
    other entity metadata files.
  - Documented columns include:
      - ``EntityID``
      - ``center_x``, ``center_y`` (microns)
  - Cell type annotations are not part of core exports; if absent we output
    ``cell_type`` as NA.

- Expression matrix:
  - ``cell_by_gene.csv`` (entity-by-gene; wide)
  - Rows are ``EntityID`` and columns are genes (and sometimes blanks).

Standardized return value matches Spatial Explorer's internal contract:

    {
        'platform': 'merscope',
        'transcript_data': DataFrame,   # columns: x, y, gene, cell_id
        'cell_metadata': DataFrame,     # columns: cell_id, x, y, cell_type
        'expression_matrix': DataFrame, # index: cell_id, columns: genes
        'metadata': dict
    }

The parser is intentionally tolerant:
- Missing files yield empty DataFrames (with expected columns) and a warning.
- Malformed files raise a ValueError with contextual detail.

T-991
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd  # type: ignore

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FileCandidates:
    transcript: Path | None
    cell_metadata: Path | None
    expression: Path | None
    json_files: list[Path]


_TRANSCRIPT_REQUIRED_OUT_COLS = ["x", "y", "gene", "cell_id"]
_CELL_REQUIRED_OUT_COLS = ["cell_id", "x", "y", "cell_type"]


def parse_merscope(input_dir: str | Path) -> dict[str, Any]:
    """Parse a directory of native MERSCOPE outputs.

    Requires the optional dependency ``pandas``.

    Parameters
    ----------
    input_dir:
        Directory path containing MERSCOPE output files.

    Returns
    -------
    dict
        Standardized Spatial Explorer structure (see module docstring).

    Raises
    ------
    FileNotFoundError
        If ``input_dir`` does not exist.
    NotADirectoryError
        If ``input_dir`` is not a directory.
    ValueError
        If a discovered file cannot be parsed or cannot be mapped to the
        standardized schema.
    """

    if pd is None:  # pragma: no cover
        raise ImportError(
            "parse_merscope requires the optional dependency 'pandas'. "
            "Install pandas to use native format parsers."
        )

    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"MERSCOPE input_dir does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"MERSCOPE input_dir is not a directory: {base}")

    candidates = _discover_files(base)

    transcript_df = _empty_transcript_df()
    cell_df = _empty_cell_metadata_df()
    expr_df = pd.DataFrame()

    if candidates.transcript is None:
        logger.warning("MERSCOPE: transcript file not found in %s", base)
    else:
        transcript_df = _load_transcripts(candidates.transcript)

    if candidates.cell_metadata is None:
        logger.warning("MERSCOPE: cell metadata file not found in %s", base)
    else:
        cell_df = _load_cell_metadata(candidates.cell_metadata)

    if candidates.expression is None:
        logger.warning("MERSCOPE: expression matrix file not found in %s", base)
    else:
        expr_df = _load_expression_matrix(candidates.expression)

    metadata = _load_metadata_json(candidates.json_files)
    metadata.setdefault("input_dir", str(base))
    metadata.setdefault(
        "files",
        {
            "transcript": str(candidates.transcript) if candidates.transcript else None,
            "cell_metadata": str(candidates.cell_metadata) if candidates.cell_metadata else None,
            "expression": str(candidates.expression) if candidates.expression else None,
            "json": [str(p) for p in candidates.json_files],
        },
    )

    _validate_transcripts(transcript_df)
    _validate_cell_metadata(cell_df)
    _validate_expression(expr_df)

    return {
        "platform": "merscope",
        "transcript_data": transcript_df,
        "cell_metadata": cell_df,
        "expression_matrix": expr_df,
        "metadata": metadata,
    }


def _discover_files(base: Path) -> _FileCandidates:
    # MERSCOPE datasets often include an analysis_outputs/ folder.
    #
    # Depending on Vizgen processing, the user may pass either:
    # - the directory that *contains* analysis_outputs/
    # - a higher-level directory that contains one or more region_* folders
    #   (each with its own analysis_outputs/)
    #
    # We prefer analysis_outputs/ when present, but we also scan the base and
    # a shallow set of likely subdirectories.
    search_roots: list[Path] = [base]

    def add_root(p: Path) -> None:
        if p.exists() and p.is_dir() and p not in search_roots:
            search_roots.append(p)

    # Prefer base/analysis_outputs
    ao = base / "analysis_outputs"
    if ao.exists() and ao.is_dir():
        search_roots.insert(0, ao)

    # Also scan analysis_outputs/ under immediate child dirs (e.g. region_0/).
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        child_ao = child / "analysis_outputs"
        if child_ao.exists() and child_ao.is_dir():
            add_root(child_ao)
        # Some exports place tables directly under region_* without the folder.
        add_root(child)

    def collect(patterns: Iterable[str]) -> list[Path]:
        out: list[Path] = []
        for root in search_roots:
            for pat in patterns:
                out.extend(root.glob(pat))
        # De-dup while preserving order
        seen: set[Path] = set()
        deduped: list[Path] = []
        for p in out:
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                deduped.append(p)
        return deduped

    tables = collect(["*.csv", "*.CSV", "*.csv.gz", "*.CSV.GZ", "*.parquet", "*.PARQUET"])

    def pick_file(preferred_names: Iterable[str], contains_any: Iterable[str]) -> Path | None:
        # Prefer exact names within any search root.
        for root in search_roots:
            lowered = {p.name.lower(): p for p in tables if p.parent == root}
            for name in preferred_names:
                p = root / name
                if p.exists():
                    return p
                if name.lower() in lowered:
                    return lowered[name.lower()]

        # Fallback: contains heuristic across all discovered tables.
        contains_any_l = [c.lower() for c in contains_any]
        for p in tables:
            n = p.name.lower()
            if any(c in n for c in contains_any_l):
                return p
        return None

    transcript = pick_file(
        preferred_names=(
            "detected_transcripts.csv",
            "detected_transcripts.parquet",
            "transcripts.csv",
            "transcripts.parquet",
        ),
        contains_any=("detected_transcripts", "transcript"),
    )

    cell_metadata = pick_file(
        preferred_names=(
            "cell_metadata.csv",
            "cell_metadata.parquet",
            "entity_metadata.csv",
            "entity_metadata_cell.csv",
            "cells.csv",
        ),
        contains_any=("cell_metadata", "entity_metadata", "cells"),
    )

    expression = pick_file(
        preferred_names=(
            "cell_by_gene.csv",
            "cell_by_gene.parquet",
            "entity_by_gene.csv",
            "expression.csv",
        ),
        contains_any=("cell_by_gene", "entity_by_gene", "by_gene", "expression"),
    )

    json_files: list[Path] = []
    for root in search_roots:
        json_files.extend(sorted(root.glob("*.json")))
        json_files.extend(sorted(root.glob("*.JSON")))

    # De-dup json files
    seen_json: set[Path] = set()
    deduped_json: list[Path] = []
    for p in json_files:
        rp = p.resolve()
        if rp not in seen_json:
            seen_json.add(rp)
            deduped_json.append(p)

    return _FileCandidates(
        transcript=transcript,
        cell_metadata=cell_metadata,
        expression=expression,
        json_files=deduped_json,
    )


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _lower_map_columns(df: pd.DataFrame) -> dict[str, str]:
    m: dict[str, str] = {}
    for c in df.columns:
        l = str(c).strip().lower()
        if l not in m:
            m[l] = c
    return m


def _empty_transcript_df() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in _TRANSCRIPT_REQUIRED_OUT_COLS})


def _empty_cell_metadata_df() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in _CELL_REQUIRED_OUT_COLS})


def _coerce_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _read_table(path: Path) -> pd.DataFrame:
    suf = "".join(path.suffixes).lower()  # handles .csv.gz
    try:
        if suf.endswith(".parquet"):
            return pd.read_parquet(path)
        if suf.endswith(".csv.gz"):
            return pd.read_csv(path, compression="gzip")
        if suf.endswith(".csv"):
            return pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"MERSCOPE: failed reading table {path}: {e}") from e

    try:
        return pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"MERSCOPE: failed reading table {path}: {e}") from e


def _load_transcripts(path: Path) -> pd.DataFrame:
    df = _read_table(path)
    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    x_col = _first_present(colmap, ["global_x", "x", "x_um", "xcoord", "x_coord"])
    y_col = _first_present(colmap, ["global_y", "y", "y_um", "ycoord", "y_coord"])
    gene_col = _first_present(colmap, ["gene", "target", "feature_name", "symbol"])

    cell_col = _first_present(colmap, ["entityid", "entity_id", "cell_id", "cellid", "cell"])

    missing = [name for name, col in [("x", x_col), ("y", y_col), ("gene", gene_col)] if col is None]
    if missing:
        raise ValueError(
            f"MERSCOPE: transcript table missing required columns {missing}. "
            f"Found columns: {list(df.columns)} (file: {path})"
        )

    cell_series = df[cell_col] if cell_col is not None else pd.NA

    # Vizgen convention: -1 means unassigned transcript.
    # Keep as NA in standardized output.
    if cell_col is not None:
        cell_numeric = pd.to_numeric(cell_series, errors="coerce")
        cell_series = cell_series.where(~(cell_numeric == -1), other=pd.NA)

    out = pd.DataFrame(
        {
            "x": df[x_col],
            "y": df[y_col],
            "gene": df[gene_col].astype(str),
            "cell_id": cell_series,
        }
    )

    out = _coerce_numeric(out, ["x", "y"])
    out["gene"] = out["gene"].astype("string")
    out["cell_id"] = out["cell_id"].astype("string")

    if out[["x", "y"]].isna().any().any():
        n = int(out[["x", "y"]].isna().any(axis=1).sum())
        logger.warning("MERSCOPE: %s transcript rows have NaN coordinates (%s)", n, path.name)

    return out


def _load_cell_metadata(path: Path) -> pd.DataFrame:
    df = _read_table(path)
    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    cell_col = _first_present(colmap, ["entityid", "entity_id", "cell_id", "cellid", "cell", "barcode"])
    x_col = _first_present(colmap, ["center_x", "x", "x_centroid", "centroid_x", "centerx"])
    y_col = _first_present(colmap, ["center_y", "y", "y_centroid", "centroid_y", "centery"])
    type_col = _first_present(
        colmap,
        [
            "cell_type",
            "celltype",
            "annotation",
            "cluster",
            "label",
            "cell_class",
        ],
    )

    if cell_col is None:
        raise ValueError(
            "MERSCOPE: cell metadata table missing required entity/cell id column. "
            f"Found columns: {list(df.columns)} (file: {path})"
        )

    out = pd.DataFrame(
        {
            "cell_id": df[cell_col].astype("string"),
            "x": df[x_col] if x_col is not None else pd.NA,
            "y": df[y_col] if y_col is not None else pd.NA,
            "cell_type": df[type_col] if type_col is not None else pd.NA,
        }
    )

    out = _coerce_numeric(out, ["x", "y"])
    out["cell_type"] = out["cell_type"].astype("string")

    if out["cell_id"].isna().any():
        n = int(out["cell_id"].isna().sum())
        logger.warning("MERSCOPE: %s cell rows have NaN cell_id (%s)", n, path.name)

    return out


def _load_expression_matrix(path: Path) -> pd.DataFrame:
    df = _read_table(path)
    df = _standardize_columns(df)

    if df.shape[1] < 2:
        raise ValueError(f"MERSCOPE: expression matrix has too few columns: {path}")

    colmap = _lower_map_columns(df)
    idx_col = _first_present(colmap, ["entityid", "entity_id", "cell_id", "cellid", "cell"]) or df.columns[0]

    expr = df.set_index(idx_col)
    expr.index.name = "cell_id"
    expr.index = expr.index.astype("string")
    expr.columns = expr.columns.astype("string")
    expr = expr.apply(pd.to_numeric, errors="coerce")

    return expr


def _load_metadata_json(json_files: list[Path]) -> dict[str, Any]:
    if not json_files:
        return {}

    meta: dict[str, Any] = {}
    for p in json_files:
        try:
            with p.open("r", encoding="utf-8") as f:
                meta[p.name] = json.load(f)
        except Exception as e:
            logger.warning("MERSCOPE: failed reading JSON metadata %s: %s", p, e)

    return meta


def _first_present(colmap: dict[str, str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colmap:
            return colmap[c]
    return None


def _validate_transcripts(df: pd.DataFrame) -> None:
    for c in _TRANSCRIPT_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"MERSCOPE: transcript_data missing required column: {c}")

    if len(df) == 0:
        return

    n_bad = int(df[["x", "y"]].isna().any(axis=1).sum())
    if n_bad:
        logger.warning("MERSCOPE: transcript_data has %s rows with missing x/y", n_bad)


def _validate_cell_metadata(df: pd.DataFrame) -> None:
    for c in _CELL_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"MERSCOPE: cell_metadata missing required column: {c}")

    if len(df) == 0:
        return

    if df["cell_id"].isna().any():
        n = int(df["cell_id"].isna().sum())
        logger.warning("MERSCOPE: cell_metadata has %s rows with missing cell_id", n)


def _validate_expression(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return

    if df.index.isna().any():
        logger.warning("MERSCOPE: expression_matrix has missing index (cell_id)")

    n_nans = int(df.isna().sum().sum())
    if n_nans:
        logger.warning("MERSCOPE: expression_matrix contains %s NaN values", n_nans)
