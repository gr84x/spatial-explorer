"""CosMx native output parser.

This module implements a lightweight, defensive parser for typical NanoString/Bruker
CosMx *native* output exports.

Expected (typical) inputs in a directory:

- Transcript table CSV (commonly named ``tx_file.csv``)
  Contains transcript coordinates and gene labels. Various exports exist; this
  parser looks for columns that can be mapped to:
    - x, y (required for standardized output)
    - gene (a.k.a. target)
    - cell_id (optional)

- Cell metadata CSV (commonly named ``cell_metadata.csv``)
  Contains per-cell centroids and annotations. We map to:
    - cell_id
    - x, y (centroid)
    - cell_type (classification / cluster / annotation)

- Expression matrix CSV (commonly named ``exprMat_file.csv``)
  Often cells × genes (wide). Some exports may be long format (cell_id, gene, count).

- One or more JSON files with run/experiment parameters.

The standardized return value matches Spatial Explorer's internal contract:

    {
        'platform': 'cosmx',
        'transcript_data': DataFrame,   # columns: x, y, gene, cell_id
        'cell_metadata': DataFrame,     # columns: cell_id, x, y, cell_type
        'expression_matrix': DataFrame, # index: cell_id, columns: genes
        'metadata': dict
    }

The parser is intentionally tolerant:
- Missing files yield empty DataFrames (with expected columns) and a warning.
- Malformed files raise a ValueError with contextual detail.

T-651
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


def parse_cosmx(input_dir: str | Path) -> dict[str, Any]:
    """Parse a directory of native CosMx outputs.

    Requires the optional dependency ``pandas``.

    Parameters
    ----------
    input_dir:
        Directory path containing CosMx output files.

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
            "parse_cosmx requires the optional dependency 'pandas'. "
            "Install pandas to use native format parsers."
        )

    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"CosMx input_dir does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"CosMx input_dir is not a directory: {base}")

    candidates = _discover_files(base)

    transcript_df = _empty_transcript_df()
    cell_df = _empty_cell_metadata_df()
    expr_df = pd.DataFrame()

    if candidates.transcript is None:
        logger.warning("CosMx: transcript file not found in %s", base)
    else:
        transcript_df = _load_transcripts(candidates.transcript)

    if candidates.cell_metadata is None:
        logger.warning("CosMx: cell metadata file not found in %s", base)
    else:
        cell_df = _load_cell_metadata(candidates.cell_metadata)

    if candidates.expression is None:
        logger.warning("CosMx: expression matrix file not found in %s", base)
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
        "platform": "cosmx",
        "transcript_data": transcript_df,
        "cell_metadata": cell_df,
        "expression_matrix": expr_df,
        "metadata": metadata,
    }


def _discover_files(base: Path) -> _FileCandidates:
    # Keep discovery rules simple and easy to adjust.
    csvs = list(base.glob("*.csv")) + list(base.glob("*.CSV"))

    def pick(preferred_names: Iterable[str], contains_any: Iterable[str]) -> Path | None:
        for name in preferred_names:
            p = base / name
            if p.exists():
                return p
        lowered = {p.name.lower(): p for p in csvs}
        for name in preferred_names:
            if name.lower() in lowered:
                return lowered[name.lower()]
        # fallback: contains heuristic
        contains_any_l = [c.lower() for c in contains_any]
        for p in csvs:
            n = p.name.lower()
            if any(c in n for c in contains_any_l):
                return p
        return None

    transcript = pick(
        preferred_names=("tx_file.csv", "transcripts.csv", "tx.csv"),
        contains_any=("tx_", "transcript"),
    )
    cell_metadata = pick(
        preferred_names=("cell_metadata.csv", "cells.csv", "cellmetadata.csv"),
        contains_any=("cell_metadata", "cellmeta", "cells"),
    )
    expression = pick(
        preferred_names=("exprMat_file.csv", "expression.csv", "exprmat.csv"),
        contains_any=("expr", "matrix"),
    )

    json_files = sorted(list(base.glob("*.json")) + list(base.glob("*.JSON")))

    return _FileCandidates(
        transcript=transcript,
        cell_metadata=cell_metadata,
        expression=expression,
        json_files=json_files,
    )


def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _lower_map_columns(df: pd.DataFrame) -> dict[str, str]:
    # Map lower->original (first occurrence wins)
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


def _load_transcripts(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"CosMx: failed reading transcript CSV: {path}: {e}") from e

    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    # Candidate columns seen in the wild / docs.
    x_col = _first_present(colmap, ["x", "x_global_px", "x_global", "x_position", "globalx", "centerx"])
    y_col = _first_present(colmap, ["y", "y_global_px", "y_global", "y_position", "globaly", "centery"])
    gene_col = _first_present(colmap, ["gene", "target", "targetname", "target_name", "feature_name"])
    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell", "cell_id", "cellid_int"])

    missing = [
        name
        for name, col in [("x", x_col), ("y", y_col), ("gene", gene_col)]
        if col is None
    ]
    if missing:
        raise ValueError(
            f"CosMx: transcript CSV missing required columns {missing}. "
            f"Found columns: {list(df.columns)} (file: {path})"
        )

    out = pd.DataFrame(
        {
            "x": df[x_col],
            "y": df[y_col],
            "gene": df[gene_col].astype(str),
            "cell_id": df[cell_col] if cell_col is not None else pd.NA,
        }
    )
    out = _coerce_numeric(out, ["x", "y"])
    out["cell_id"] = out["cell_id"].astype("string")
    out["gene"] = out["gene"].astype("string")

    # Lightweight quality warnings.
    if out[["x", "y"]].isna().any().any():
        n = int(out[["x", "y"]].isna().any(axis=1).sum())
        logger.warning("CosMx: %s transcript rows have NaN coordinates (%s)", n, path.name)
    if out["gene"].isna().any():
        n = int(out["gene"].isna().sum())
        logger.warning("CosMx: %s transcript rows have NaN gene labels (%s)", n, path.name)

    return out


def _load_cell_metadata(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"CosMx: failed reading cell metadata CSV: {path}: {e}") from e

    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell", "cell_id_int"])
    x_col = _first_present(colmap, ["x", "centerx", "centroid_x", "centroidx", "x_center"])
    y_col = _first_present(colmap, ["y", "centery", "centroid_y", "centroidy", "y_center"])
    type_col = _first_present(
        colmap,
        [
            "cell_type",
            "celltype",
            "cell_class",
            "classification",
            "cluster",
            "annotation",
            "celltype_label",
        ],
    )

    if cell_col is None:
        raise ValueError(
            f"CosMx: cell metadata CSV missing required cell id column. "
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
        logger.warning("CosMx: %s cell rows have NaN cell_id (%s)", n, path.name)

    return out


def _load_expression_matrix(path: Path) -> pd.DataFrame:
    """Load expression matrix.

    Supports two shapes:
    1) Wide: first column is cell_id and remaining columns are genes.
    2) Long: columns include (cell_id, gene, count) and are pivoted.

    Notes on memory:
    - This implementation uses pandas; for truly large matrices a future
      improvement would support chunked loading and sparse output.
    """

    try:
        df = pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"CosMx: failed reading expression matrix CSV: {path}: {e}") from e

    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    # Long format detection.
    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell"])
    gene_col = _first_present(colmap, ["gene", "target", "feature", "feature_name"])
    count_col = _first_present(colmap, ["count", "counts", "umi", "umis", "value", "expr"])

    if cell_col is not None and gene_col is not None and count_col is not None and len(df.columns) <= 6:
        long = df[[cell_col, gene_col, count_col]].copy()
        long.columns = ["cell_id", "gene", "count"]
        long["cell_id"] = long["cell_id"].astype("string")
        long["gene"] = long["gene"].astype("string")
        long["count"] = pd.to_numeric(long["count"], errors="coerce")
        if long[["cell_id", "gene"]].isna().any().any():
            logger.warning("CosMx: expression long table has NaNs in key columns (%s)", path.name)
        expr = long.pivot_table(index="cell_id", columns="gene", values="count", aggfunc="sum", fill_value=0)
        # pivot_table returns columns Index; keep as DataFrame
        return expr

    # Wide format.
    # Heuristic: first column is cell id if it looks like an identifier column.
    if df.shape[1] < 2:
        raise ValueError(f"CosMx: expression matrix has too few columns: {path}")

    first = str(df.columns[0]).strip().lower()
    if first in {"cell_id", "cellid", "cell", "cellid_int"}:
        expr = df.set_index(df.columns[0])
        expr.index = expr.index.astype("string")
        # Coerce all counts to numeric
        expr = expr.apply(pd.to_numeric, errors="coerce")
        return expr

    # Some exports put genes in first column and cell IDs as headers.
    if first in {"gene", "target", "feature", "feature_name"}:
        expr = df.set_index(df.columns[0]).T
        expr.index.name = "cell_id"
        expr.index = expr.index.astype("string")
        expr.columns = expr.columns.astype("string")
        expr = expr.apply(pd.to_numeric, errors="coerce")
        return expr

    # Fall back: try interpret first column as index anyway.
    expr = df.set_index(df.columns[0])
    expr.index = expr.index.astype("string")
    expr = expr.apply(pd.to_numeric, errors="coerce")
    logger.warning(
        "CosMx: expression matrix format ambiguous; assumed first column is index (%s)",
        path.name,
    )
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
            logger.warning("CosMx: failed reading JSON metadata %s: %s", p, e)

    return meta


def _first_present(colmap: dict[str, str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colmap:
            return colmap[c]
    return None


def _validate_transcripts(df: pd.DataFrame) -> None:
    for c in _TRANSCRIPT_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"CosMx: transcript_data missing required column: {c}")

    if len(df) == 0:
        return

    # Count NaNs in required coordinate columns.
    n_bad = int(df[["x", "y"]].isna().any(axis=1).sum())
    if n_bad:
        logger.warning("CosMx: transcript_data has %s rows with missing x/y", n_bad)

    # Coordinate bounds sanity: warn if coordinates look wildly out of expected pixel/mm scales.
    # We avoid hard-failing because scale depends on export units.
    x = pd.to_numeric(df["x"], errors="coerce")
    y = pd.to_numeric(df["y"], errors="coerce")
    if x.notna().any() and y.notna().any():
        if (x.abs().max() > 1e7) or (y.abs().max() > 1e7):
            logger.warning(
                "CosMx: transcript coordinates have very large magnitude (max|x|=%s, max|y|=%s)",
                float(x.abs().max()),
                float(y.abs().max()),
            )


def _validate_cell_metadata(df: pd.DataFrame) -> None:
    for c in _CELL_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"CosMx: cell_metadata missing required column: {c}")

    if len(df) == 0:
        return

    if df["cell_id"].isna().any():
        n = int(df["cell_id"].isna().sum())
        logger.warning("CosMx: cell_metadata has %s rows with missing cell_id", n)


def _validate_expression(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return

    # Ensure index is present and numeric values are reasonable.
    if df.index.isna().any():
        logger.warning("CosMx: expression_matrix has missing index (cell_id)")

    # Warn if many NaNs exist after coercion.
    n_nans = int(df.isna().sum().sum())
    if n_nans:
        logger.warning("CosMx: expression_matrix contains %s NaN values", n_nans)
