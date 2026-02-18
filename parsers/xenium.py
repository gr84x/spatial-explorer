"""Xenium native output parser.

This module implements a lightweight, defensive parser for typical 10x Genomics
Xenium *native* output exports.

Typical Xenium output files (may vary by software version / export options):

- Transcripts table:
  - ``transcripts.parquet`` or ``transcripts.csv.gz``
  - Expected columns include (see 10x docs):
      - ``x_location``, ``y_location`` (microns)
      - ``feature_name`` (gene/control name)
      - ``cell_id`` (optional for unassigned transcripts; often present)

- Cell metadata:
  - ``cells.parquet`` or ``cells.csv.gz``
  - Expected columns include:
      - ``cell_id``
      - ``x_centroid``, ``y_centroid`` (microns)
    Cell type annotations are not always present in ``cells.*``; if missing we
    output ``cell_type`` as NA.

- Expression matrix (cell × gene counts):
  - ``cell_feature_matrix.h5`` (10x HDF5 sparse matrix) or
  - ``cell_feature_matrix/`` directory containing ``matrix.mtx(.gz)``,
    ``barcodes.tsv(.gz)``, ``features.tsv(.gz)``.
  - Some exports may provide a CSV/TSV matrix.

- Metadata:
  - ``experiment.xenium`` (JSON manifest) and/or other ``*.json`` files.

The standardized return value matches Spatial Explorer's internal contract:

    {
        'platform': 'xenium',
        'transcript_data': DataFrame,   # columns: x, y, gene, cell_id
        'cell_metadata': DataFrame,     # columns: cell_id, x, y, cell_type
        'expression_matrix': DataFrame, # index: cell_id, columns: genes
        'metadata': dict
    }

The parser is intentionally tolerant:
- Missing files yield empty DataFrames (with expected columns) and a warning.
- Malformed files raise a ValueError with contextual detail.

T-652
"""

from __future__ import annotations

import gzip
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
    expression: Path | None  # file (h5/csv) or directory (mtx)
    json_files: list[Path]


_TRANSCRIPT_REQUIRED_OUT_COLS = ["x", "y", "gene", "cell_id"]
_CELL_REQUIRED_OUT_COLS = ["cell_id", "x", "y", "cell_type"]


def parse_xenium(input_dir: str | Path) -> dict[str, Any]:
    """Parse a directory of native Xenium outputs.

    Parameters
    ----------
    input_dir:
        Directory path containing Xenium output files.

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

    Notes
    -----
    Requires the optional dependency ``pandas``.
    """

    if pd is None:  # pragma: no cover
        raise ImportError(
            "parse_xenium requires the optional dependency 'pandas'. "
            "Install pandas (and optionally pyarrow/h5py/scipy) to parse Xenium outputs."
        )

    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"Xenium input_dir does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Xenium input_dir is not a directory: {base}")

    candidates = _discover_files(base)

    transcript_df = _empty_transcript_df()
    cell_df = _empty_cell_metadata_df()
    expr_df = pd.DataFrame()

    if candidates.transcript is None:
        logger.warning("Xenium: transcript file not found in %s", base)
    else:
        transcript_df = _load_transcripts(candidates.transcript)

    if candidates.cell_metadata is None:
        logger.warning("Xenium: cell metadata file not found in %s", base)
    else:
        cell_df = _load_cell_metadata(candidates.cell_metadata)

    if candidates.expression is None:
        logger.warning("Xenium: expression matrix not found in %s", base)
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
        "platform": "xenium",
        "transcript_data": transcript_df,
        "cell_metadata": cell_df,
        "expression_matrix": expr_df,
        "metadata": metadata,
    }


def _discover_files(base: Path) -> _FileCandidates:
    # Xenium exports are often a mix of parquet, gzipped CSV, and directories.
    parquet = list(base.glob("*.parquet")) + list(base.glob("*.PARQUET"))
    csvs = (
        list(base.glob("*.csv"))
        + list(base.glob("*.CSV"))
        + list(base.glob("*.csv.gz"))
        + list(base.glob("*.CSV.GZ"))
    )

    def pick_file(preferred_names: Iterable[str], contains_any: Iterable[str], pool: list[Path]) -> Path | None:
        for name in preferred_names:
            p = base / name
            if p.exists():
                return p
        lowered = {p.name.lower(): p for p in pool}
        for name in preferred_names:
            if name.lower() in lowered:
                return lowered[name.lower()]
        contains_any_l = [c.lower() for c in contains_any]
        for p in pool:
            n = p.name.lower()
            if any(c in n for c in contains_any_l):
                return p
        return None

    transcript = pick_file(
        preferred_names=("transcripts.parquet", "transcripts.csv.gz", "transcripts.csv"),
        contains_any=("transcripts",),
        pool=parquet + csvs,
    )
    cell_metadata = pick_file(
        preferred_names=("cells.parquet", "cells.csv.gz", "cells.csv"),
        contains_any=("cells", "cell_summary"),
        pool=parquet + csvs,
    )

    # Expression can be either an H5 file or a directory.
    expr: Path | None = None
    for name in ("cell_feature_matrix.h5", "cell_feature_matrix.H5"):
        p = base / name
        if p.exists():
            expr = p
            break

    if expr is None:
        # Look for a directory named cell_feature_matrix
        d = base / "cell_feature_matrix"
        if d.exists() and d.is_dir():
            expr = d
        else:
            # fallback: any .h5 that looks like a matrix
            h5s = list(base.glob("*.h5")) + list(base.glob("*.H5"))
            for p in h5s:
                if "feature_matrix" in p.name.lower() or "cell_feature" in p.name.lower():
                    expr = p
                    break

    json_files = sorted(
        list(base.glob("*.json"))
        + list(base.glob("*.JSON"))
        + list(base.glob("*.xenium"))
        + list(base.glob("*.XENIUM"))
    )

    return _FileCandidates(
        transcript=transcript,
        cell_metadata=cell_metadata,
        expression=expr,
        json_files=json_files,
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
    """Read CSV/CSV.GZ or Parquet."""
    suf = "".join(path.suffixes).lower()  # handles .csv.gz
    try:
        if suf.endswith(".parquet"):
            return pd.read_parquet(path)
        if suf.endswith(".csv"):
            return pd.read_csv(path)
        if suf.endswith(".csv.gz"):
            return pd.read_csv(path, compression="gzip")
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Xenium: failed reading table {path}: {e}") from e

    # fallback: try pandas reader by suffix
    try:
        return pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Xenium: failed reading table {path}: {e}") from e


def _load_transcripts(path: Path) -> pd.DataFrame:
    df = _read_table(path)
    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    x_col = _first_present(colmap, ["x", "x_location", "x_um", "xcoord", "x_coord"])
    y_col = _first_present(colmap, ["y", "y_location", "y_um", "ycoord", "y_coord"])
    gene_col = _first_present(colmap, ["gene", "feature_name", "feature", "target", "symbol"])
    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell", "cell_id_int"])

    missing = [name for name, col in [("x", x_col), ("y", y_col), ("gene", gene_col)] if col is None]
    if missing:
        raise ValueError(
            f"Xenium: transcript table missing required columns {missing}. "
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

    if out[["x", "y"]].isna().any().any():
        n = int(out[["x", "y"]].isna().any(axis=1).sum())
        logger.warning("Xenium: %s transcript rows have NaN coordinates (%s)", n, path.name)

    return out


def _load_cell_metadata(path: Path) -> pd.DataFrame:
    df = _read_table(path)
    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell", "barcode"])
    x_col = _first_present(colmap, ["x", "x_centroid", "centroid_x", "centerx"])
    y_col = _first_present(colmap, ["y", "y_centroid", "centroid_y", "centery"])
    type_col = _first_present(
        colmap,
        [
            "cell_type",
            "celltype",
            "annotation",
            "cluster",
            "graphclust",
            "kmeans",
            "label",
        ],
    )

    if cell_col is None:
        raise ValueError(
            f"Xenium: cell metadata table missing required cell id column. "
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
        logger.warning("Xenium: %s cell rows have NaN cell_id (%s)", n, path.name)

    return out


def _load_expression_matrix(path: Path) -> pd.DataFrame:
    """Load Xenium expression matrix.

    Supported inputs:
    - 10x H5 matrix (``cell_feature_matrix.h5``)
    - 10x MEX directory (``cell_feature_matrix/``)
    - CSV/TSV matrices (wide or long) using the same heuristics as CosMx.

    Returns a pandas DataFrame with index=cell_id, columns=genes.

    Notes on memory:
    - If scipy is available, H5/MEX are loaded as sparse and returned using
      pandas' sparse arrays.
    """

    if path.is_dir():
        return _load_mex_dir(path)

    suf = "".join(path.suffixes).lower()
    if suf.endswith(".h5"):
        return _load_10x_h5(path)

    # Fallback: CSV-like expression matrix
    return _load_expression_table_csv(path)


def _load_expression_table_csv(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Xenium: failed reading expression matrix: {path}: {e}") from e

    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    cell_col = _first_present(colmap, ["cell_id", "cellid", "cell", "barcode"])
    gene_col = _first_present(colmap, ["gene", "feature", "feature_name", "symbol"])
    count_col = _first_present(colmap, ["count", "counts", "umi", "umis", "value", "expr"])

    # Long format detection
    if cell_col is not None and gene_col is not None and count_col is not None and len(df.columns) <= 6:
        long = df[[cell_col, gene_col, count_col]].copy()
        long.columns = ["cell_id", "gene", "count"]
        long["cell_id"] = long["cell_id"].astype("string")
        long["gene"] = long["gene"].astype("string")
        long["count"] = pd.to_numeric(long["count"], errors="coerce")
        expr = long.pivot_table(index="cell_id", columns="gene", values="count", aggfunc="sum", fill_value=0)
        return expr

    # Wide format
    if df.shape[1] < 2:
        raise ValueError(f"Xenium: expression matrix has too few columns: {path}")

    first = str(df.columns[0]).strip().lower()
    if first in {"cell_id", "cellid", "cell", "barcode"}:
        expr = df.set_index(df.columns[0])
        expr.index = expr.index.astype("string")
        expr = expr.apply(pd.to_numeric, errors="coerce")
        return expr

    if first in {"gene", "feature", "feature_name", "symbol"}:
        expr = df.set_index(df.columns[0]).T
        expr.index.name = "cell_id"
        expr.index = expr.index.astype("string")
        expr.columns = expr.columns.astype("string")
        expr = expr.apply(pd.to_numeric, errors="coerce")
        return expr

    expr = df.set_index(df.columns[0])
    expr.index = expr.index.astype("string")
    expr = expr.apply(pd.to_numeric, errors="coerce")
    logger.warning("Xenium: expression matrix format ambiguous; assumed first column is index (%s)", path.name)
    return expr


def _load_10x_h5(path: Path) -> pd.DataFrame:
    """Load a 10x HDF5 sparse matrix.

    We prefer using scipy for efficient sparse handling, but fall back to a
    dense loader when scipy isn't available (useful in lightweight
    environments). The dense fallback is guarded by a size limit to avoid
    accidental huge allocations.
    """

    try:
        import h5py  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ValueError(
            "Xenium: reading cell_feature_matrix.h5 requires the optional dependency 'h5py'. "
            f"Install h5py or provide CSV/MEX instead. (file: {path})"
        ) from e

    # scipy is optional: if missing we'll attempt a dense fallback.
    try:
        import scipy.sparse  # type: ignore
    except Exception:  # pragma: no cover
        scipy = None  # type: ignore[assignment]

    try:
        with h5py.File(path, "r") as f:
            if "matrix" not in f:
                raise ValueError(f"Xenium: H5 missing /matrix group: {path}")
            g = f["matrix"]

            data = g["data"][:]
            indices = g["indices"][:]
            indptr = g["indptr"][:]
            shape = tuple(g["shape"][:])

            # Features
            feat_g = g.get("features")
            if feat_g is None:
                raise ValueError(f"Xenium: H5 missing /matrix/features: {path}")

            # 10x can store names as 'name' or 'feature_name'
            if "name" in feat_g:
                feature_names = feat_g["name"][:]
            elif "feature_name" in feat_g:
                feature_names = feat_g["feature_name"][:]
            else:
                # fallback: first dataset
                k0 = list(feat_g.keys())[0]
                feature_names = feat_g[k0][:]

            # Barcodes (cell IDs)
            barcodes = g["barcodes"][:]

    except ValueError:
        raise
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Xenium: failed reading H5 matrix {path}: {e}") from e

    # Decode bytes to str
    def _decode(a: Any) -> list[str]:
        out: list[str] = []
        for v in a:
            if isinstance(v, (bytes, bytearray)):
                out.append(v.decode("utf-8"))
            else:
                out.append(str(v))
        return out

    genes = _decode(feature_names)
    cells = _decode(barcodes)

    n_features, n_barcodes = int(shape[0]), int(shape[1])

    # 10x H5 is CSC: shape = (n_features, n_barcodes)
    if scipy is not None:
        mat = scipy.sparse.csc_matrix((data, indices, indptr), shape=(n_features, n_barcodes))
        # Convert to cells x genes
        mat_csr = mat.T.tocsr()
        expr = pd.DataFrame.sparse.from_spmatrix(
            mat_csr,
            index=pd.Index(cells, name="cell_id"),
            columns=pd.Index(genes, name="gene"),
        )
        return expr

    # Dense fallback (no scipy). Safe for small example datasets.
    import numpy as np  # type: ignore

    # Guardrail: avoid allocating an enormous dense matrix silently.
    max_elements = 50_000_000  # ~200MB for float32
    if n_features * n_barcodes > max_elements:
        raise ValueError(
            "Xenium: reading cell_feature_matrix.h5 without scipy would require allocating a huge dense matrix. "
            "Install the optional dependency 'scipy' for sparse loading, or export a smaller matrix. "
            f"(features={n_features}, barcodes={n_barcodes}, file={path})"
        )

    logger.warning(
        "Xenium: scipy not installed; loading H5 expression matrix as dense (features=%s, barcodes=%s)",
        n_features,
        n_barcodes,
    )

    dense = np.zeros((n_barcodes, n_features), dtype=np.float32)
    # indptr describes column starts for CSC (each barcode is a column)
    for col in range(n_barcodes):
        start = int(indptr[col])
        end = int(indptr[col + 1])
        if end <= start:
            continue
        rows = indices[start:end]
        vals = data[start:end]
        dense[col, rows] = vals

    expr = pd.DataFrame(dense, index=pd.Index(cells, name="cell_id"), columns=pd.Index(genes, name="gene"))
    return expr


def _load_mex_dir(path: Path) -> pd.DataFrame:
    # Load the 10x MEX directory using scipy if available.
    try:
        import scipy.io  # type: ignore
        import scipy.sparse  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ValueError(
            "Xenium: reading a cell_feature_matrix/ MEX directory requires the optional dependency 'scipy'. "
            f"Install scipy or provide H5/CSV instead. (dir: {path})"
        ) from e

    matrix_path = _first_existing(
        [
            path / "matrix.mtx.gz",
            path / "matrix.mtx",
        ]
    )
    barcodes_path = _first_existing([path / "barcodes.tsv.gz", path / "barcodes.tsv"])
    features_path = _first_existing([path / "features.tsv.gz", path / "features.tsv", path / "genes.tsv.gz", path / "genes.tsv"])

    if matrix_path is None or barcodes_path is None or features_path is None:
        raise ValueError(
            "Xenium: MEX directory missing required files. "
            f"Need matrix.mtx(.gz), barcodes.tsv(.gz), features.tsv(.gz). (dir: {path})"
        )

    try:
        mat = scipy.io.mmread(str(matrix_path))
        mat = mat.tocsc()
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Xenium: failed reading MEX matrix {matrix_path}: {e}") from e

    barcodes = _read_tsv_first_col(barcodes_path)
    features = _read_tsv_first_col(features_path, prefer_second_col=True)

    # MEX matrix is features x barcodes
    mat_csr = mat.T.tocsr()
    expr = pd.DataFrame.sparse.from_spmatrix(mat_csr, index=pd.Index(barcodes, name="cell_id"), columns=pd.Index(features, name="gene"))
    return expr


def _read_tsv_first_col(path: Path, prefer_second_col: bool = False) -> list[str]:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:  # type: ignore[arg-type]
        rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]

    if not rows:
        return []

    if prefer_second_col and len(rows[0]) >= 2:
        # features.tsv: col1=id, col2=name, col3=type
        return [r[1] for r in rows]

    return [r[0] for r in rows]


def _load_metadata_json(json_files: list[Path]) -> dict[str, Any]:
    if not json_files:
        return {}

    meta: dict[str, Any] = {}
    for p in json_files:
        try:
            with p.open("r", encoding="utf-8") as f:
                meta[p.name] = json.load(f)
        except Exception as e:
            logger.warning("Xenium: failed reading JSON metadata %s: %s", p, e)

    return meta


def _first_present(colmap: dict[str, str], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in colmap:
            return colmap[c]
    return None


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def _validate_transcripts(df: pd.DataFrame) -> None:
    for c in _TRANSCRIPT_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"Xenium: transcript_data missing required column: {c}")

    if len(df) == 0:
        return

    n_bad = int(df[["x", "y"]].isna().any(axis=1).sum())
    if n_bad:
        logger.warning("Xenium: transcript_data has %s rows with missing x/y", n_bad)


def _validate_cell_metadata(df: pd.DataFrame) -> None:
    for c in _CELL_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"Xenium: cell_metadata missing required column: {c}")

    if len(df) == 0:
        return

    if df["cell_id"].isna().any():
        n = int(df["cell_id"].isna().sum())
        logger.warning("Xenium: cell_metadata has %s rows with missing cell_id", n)


def _validate_expression(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return

    if df.index.isna().any():
        logger.warning("Xenium: expression_matrix has missing index (cell_id)")

    n_nans = int(df.isna().sum().sum())
    if n_nans:
        logger.warning("Xenium: expression_matrix contains %s NaN values", n_nans)
