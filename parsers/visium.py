"""Visium (10x Genomics) spatial gene expression output parser.

This module implements a lightweight, defensive parser for typical 10x Genomics
Visium *Space Ranger* output directories.

Common directory layout (Space Ranger):

- Spatial coordinates (spot metadata):
  - ``spatial/tissue_positions.csv`` (newer)
  - ``spatial/tissue_positions_list.csv`` (older)
    Columns:
      barcode, in_tissue, array_row, array_col, pxl_row_in_fullres, pxl_col_in_fullres

- Expression matrix (feature × barcode counts):
  - ``filtered_feature_bc_matrix.h5`` (optional)
  - ``filtered_feature_bc_matrix/`` MEX directory with:
      matrix.mtx(.gz), features.tsv(.gz), barcodes.tsv(.gz)
  - (fallback) ``raw_feature_bc_matrix/`` similar layout

- Optional metadata:
  - ``spatial/scalefactors_json.json``
  - other ``*.json`` files

Standardized return value matches Spatial Explorer's internal contract:

    {
        'platform': 'visium',
        'transcript_data': DataFrame,   # empty (Visium doesn't provide per-transcript coords)
        'cell_metadata': DataFrame,     # spot table mapped to: cell_id, x, y, cell_type
        'expression_matrix': DataFrame, # index: cell_id (barcode), columns: genes
        'metadata': dict
    }

Notes
-----
Visium matrices are typically very wide (20k+ genes). In many environments,
loading them without ``scipy`` is memory-prohibitive. This parser includes a
pure-Python Matrix Market reader which builds a *dense* numpy array and will
raise a ValueError when the matrix is too large, recommending installing
``scipy`` for sparse loading.

T-988
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TextIO, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd  # type: ignore

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FileCandidates:
    tissue_positions: Path | None
    expression: Path | None  # directory (MEX) or .h5 file
    json_files: list[Path]


_TRANSCRIPT_REQUIRED_OUT_COLS = ["x", "y", "gene", "cell_id"]
_CELL_REQUIRED_OUT_COLS = ["cell_id", "x", "y", "cell_type"]

# Without scipy, we only support dense loading of relatively small matrices.
# Limit is the number of matrix entries (n_features * n_barcodes).
_MAX_DENSE_ENTRIES = 20_000_000


def parse_visium(input_dir: str | Path) -> dict[str, Any]:
    """Parse a directory of native Visium (Space Ranger) outputs.

    Requires the optional dependency ``pandas``.
    """

    if pd is None:  # pragma: no cover
        raise ImportError(
            "parse_visium requires the optional dependency 'pandas'. "
            "Install pandas to use native format parsers."
        )

    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"Visium input_dir does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Visium input_dir is not a directory: {base}")

    candidates = _discover_files(base)

    transcript_df = _empty_transcript_df()  # Visium has no transcript coords.
    cell_df = _empty_cell_metadata_df()
    expr_df = pd.DataFrame()

    if candidates.tissue_positions is None:
        logger.warning("Visium: tissue_positions file not found in %s", base)
    else:
        cell_df = _load_tissue_positions(candidates.tissue_positions)

    if candidates.expression is None:
        logger.warning("Visium: expression matrix not found in %s", base)
    else:
        expr_df = _load_expression_matrix(candidates.expression)

    metadata = _load_metadata_json(candidates.json_files)
    metadata.setdefault("input_dir", str(base))
    metadata.setdefault(
        "files",
        {
            "tissue_positions": str(candidates.tissue_positions) if candidates.tissue_positions else None,
            "expression": str(candidates.expression) if candidates.expression else None,
            "json": [str(p) for p in candidates.json_files],
        },
    )

    _validate_transcripts(transcript_df)
    _validate_cell_metadata(cell_df)
    _validate_expression(expr_df)

    return {
        "platform": "visium",
        "transcript_data": transcript_df,
        "cell_metadata": cell_df,
        "expression_matrix": expr_df,
        "metadata": metadata,
    }


def _discover_files(base: Path) -> _FileCandidates:
    spatial_dir = base / "spatial"

    tissue_positions: Path | None = None
    if spatial_dir.exists() and spatial_dir.is_dir():
        for name in ("tissue_positions.csv", "tissue_positions_list.csv"):
            p = spatial_dir / name
            if p.exists():
                tissue_positions = p
                break

    # Expression: prefer filtered, fall back to raw.
    expr: Path | None = None
    for name in (
        "filtered_feature_bc_matrix.h5",
        "filtered_feature_bc_matrix",
        "raw_feature_bc_matrix.h5",
        "raw_feature_bc_matrix",
    ):
        p = base / name
        if p.exists():
            expr = p
            break

    json_files: list[Path] = []
    if spatial_dir.exists() and spatial_dir.is_dir():
        json_files.extend(list(spatial_dir.glob("*.json")) + list(spatial_dir.glob("*.JSON")))
    json_files.extend(list(base.glob("*.json")) + list(base.glob("*.JSON")))

    return _FileCandidates(
        tissue_positions=tissue_positions,
        expression=expr,
        json_files=sorted({p.resolve() for p in json_files}),
    )


def _empty_transcript_df() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in _TRANSCRIPT_REQUIRED_OUT_COLS})


def _empty_cell_metadata_df() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in _CELL_REQUIRED_OUT_COLS})


def _read_text_maybe_gz(path: Path) -> TextIO:
    if "".join(path.suffixes).lower().endswith(".gz"):
        return gzip.open(path, mode="rt", encoding="utf-8", newline="")
    return open(path, mode="rt", encoding="utf-8", newline="")


def _load_tissue_positions(path: Path) -> pd.DataFrame:
    try:
        # Space Ranger tissue_positions*.csv typically has no header in older
        # versions (tissue_positions_list.csv). Newer tissue_positions.csv has
        # a header. We handle both.
        df = pd.read_csv(path, header=0, sep=None, engine="python")
        # If the first column isn't barcode-like, treat as headerless.
        if df.shape[1] == 6 and str(df.columns[0]).strip().lower() != "barcode":
            raise ValueError("headerless")
    except Exception:
        df = pd.read_csv(
            path,
            sep=None,
            engine="python",
            header=None,
            names=[
                "barcode",
                "in_tissue",
                "array_row",
                "array_col",
                "pxl_row_in_fullres",
                "pxl_col_in_fullres",
            ],
        )

    cols = [str(c).strip() for c in df.columns]
    df.columns = cols
    col_lut = {c.lower(): c for c in df.columns}

    barcode_col = col_lut.get("barcode")
    px_row_col = col_lut.get("pxl_row_in_fullres")
    px_col_col = col_lut.get("pxl_col_in_fullres")

    missing = [
        name
        for name, col in [("barcode", barcode_col), ("pxl_row_in_fullres", px_row_col), ("pxl_col_in_fullres", px_col_col)]
        if col is None
    ]
    if missing:
        raise ValueError(f"Visium: tissue_positions missing required columns: {missing} (file: {path})")

    out = pd.DataFrame(
        {
            "cell_id": df[barcode_col].astype(str),
            # Use full-resolution pixel coordinates; Spatial Explorer treats units as arbitrary.
            "x": pd.to_numeric(df[px_col_col], errors="coerce"),
            "y": pd.to_numeric(df[px_row_col], errors="coerce"),
            "cell_type": pd.Series([pd.NA] * len(df), dtype="object"),
        }
    )

    return out


def _load_expression_matrix(path: Path) -> pd.DataFrame:
    # Support MEX directory; H5 requires optional deps.
    if path.is_dir():
        return _load_mex_dir(path)

    suf = "".join(path.suffixes).lower()
    if suf.endswith(".h5"):
        raise ValueError(
            "Visium: reading *.h5 matrices requires optional dependencies (e.g., h5py/scipy). "
            f"Provide a filtered_feature_bc_matrix/ MEX directory instead. (file: {path})"
        )

    raise ValueError(f"Visium: unsupported expression matrix path: {path}")


def _first_existing(base: Path, names: Iterable[str]) -> Path | None:
    for n in names:
        p = base / n
        if p.exists():
            return p
        # case-insensitive
        lower = {c.name.lower(): c for c in base.iterdir()} if base.exists() else {}
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _load_mex_dir(path: Path) -> pd.DataFrame:
    matrix_path = _first_existing(path, ["matrix.mtx.gz", "matrix.mtx"])
    features_path = _first_existing(path, ["features.tsv.gz", "features.tsv", "genes.tsv.gz", "genes.tsv"])
    barcodes_path = _first_existing(path, ["barcodes.tsv.gz", "barcodes.tsv"])

    missing = [
        name
        for name, p in [("matrix.mtx(.gz)", matrix_path), ("features.tsv(.gz)", features_path), ("barcodes.tsv(.gz)", barcodes_path)]
        if p is None
    ]
    if missing:
        raise ValueError(f"Visium: MEX directory missing required files: {missing} (dir: {path})")

    features = _read_tsv_first_or_second_col(features_path)
    barcodes = _read_tsv_first_col(barcodes_path)

    mat = _read_matrix_market_dense(matrix_path, max_dense_entries=_MAX_DENSE_ENTRIES)
    # 10x convention: matrix is features (rows) x barcodes (cols)
    if mat.shape != (len(features), len(barcodes)):
        raise ValueError(
            "Visium: matrix.mtx shape does not match features/barcodes: "
            f"matrix={mat.shape}, features={len(features)}, barcodes={len(barcodes)} (file: {matrix_path})"
        )

    # Convert to cells x genes DataFrame
    df = pd.DataFrame(mat.T, index=pd.Index(barcodes, name="cell_id"), columns=pd.Index(features, name="gene"))
    return df


def _read_tsv_first_col(path: Path) -> list[str]:
    out: list[str] = []
    with _read_text_maybe_gz(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            out.append(line.split("\t")[0])
    return out


def _read_tsv_first_or_second_col(path: Path) -> list[str]:
    # features.tsv typically: feature_id, feature_name, feature_type
    out: list[str] = []
    with _read_text_maybe_gz(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].strip():
                out.append(parts[1])
            else:
                out.append(parts[0])
    return out


def _read_matrix_market_dense(path: Path, max_dense_entries: int) -> np.ndarray:
    """Read a Matrix Market coordinate matrix into a dense numpy array.

    Raises ValueError when the matrix is too large for dense loading.
    """

    with _read_text_maybe_gz(path) as f:
        header = f.readline()
        if not header.startswith("%%MatrixMarket"):
            raise ValueError(f"Visium: not a MatrixMarket file: {path}")

        # Skip comments
        line = f.readline()
        while line.startswith("%"):
            line = f.readline()
        dims = line.strip().split()
        if len(dims) != 3:
            raise ValueError(f"Visium: invalid MatrixMarket dims line: {line!r} (file: {path})")

        n_rows, n_cols, n_entries = (int(dims[0]), int(dims[1]), int(dims[2]))

        if n_rows * n_cols > max_dense_entries:
            raise ValueError(
                "Visium: matrix is too large to load densely without scipy. "
                f"shape=({n_rows},{n_cols}) entries={n_rows*n_cols}. "
                "Install 'scipy' for sparse loading or export a smaller panel. "
                f"(file: {path})"
            )

        mat = np.zeros((n_rows, n_cols), dtype=np.int32)

        for i in range(n_entries):
            row = f.readline()
            if not row:
                raise ValueError(f"Visium: unexpected EOF reading MatrixMarket entries (read {i}/{n_entries}) (file: {path})")
            parts = row.strip().split()
            if len(parts) < 3:
                raise ValueError(f"Visium: invalid MatrixMarket entry line: {row!r} (file: {path})")
            r = int(parts[0]) - 1
            c = int(parts[1]) - 1
            v = float(parts[2])
            if r < 0 or c < 0 or r >= n_rows or c >= n_cols:
                raise ValueError(f"Visium: entry index out of bounds: {(r+1,c+1)} for shape {(n_rows,n_cols)} (file: {path})")
            mat[r, c] = int(v)

    return mat


def _load_metadata_json(json_files: list[Path]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in json_files:
        try:
            out[p.name] = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover
            logger.warning("Visium: failed to read json %s: %s", p, e)
    return out


def _validate_transcripts(df: pd.DataFrame) -> None:
    missing = [c for c in _TRANSCRIPT_REQUIRED_OUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Visium: transcript_data missing required columns: {missing}")


def _validate_cell_metadata(df: pd.DataFrame) -> None:
    missing = [c for c in _CELL_REQUIRED_OUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Visium: cell_metadata missing required columns: {missing}")


def _validate_expression(df: pd.DataFrame) -> None:
    if df.empty:
        return
    if df.index.name != "cell_id":
        # Keep lenient; but ensure index is set.
        return
