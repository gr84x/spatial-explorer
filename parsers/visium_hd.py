"""Visium HD (10x Genomics Space Ranger) output parser.

This module implements a lightweight, defensive parser for typical 10x Genomics
Visium HD outputs (Space Ranger).

Visium HD differs from platforms like Xenium/CosMx in that the primary
expression units are *bins* (or spots), not individual transcripts. As a
result:

- ``transcript_data`` is returned as an empty DataFrame by default.
- ``cell_metadata`` represents bins/spots and their coordinates.
- ``expression_matrix`` is a bin/spot × gene matrix.

Typical Space Ranger/Visium HD structures (varies by version/options):

- Standard Visium output:
  - ``filtered_feature_bc_matrix.h5`` OR ``filtered_feature_bc_matrix/`` (MEX)
  - ``spatial/tissue_positions.csv`` or ``spatial/tissue_positions_list.csv``

- Visium HD binned outputs:
  - ``binned_outputs/<bin>/filtered_feature_bc_matrix.h5`` OR directory MEX
  - ``binned_outputs/<bin>/spatial/tissue_positions*.csv``

This parser discovers a suitable output root and normalizes the data to
Spatial Explorer's internal contract:

    {
        'platform': 'visium_hd',
        'transcript_data': DataFrame,   # columns: x, y, gene, cell_id (empty)
        'cell_metadata': DataFrame,     # columns: cell_id, x, y, cell_type
        'expression_matrix': DataFrame, # index: cell_id, columns: genes
        'metadata': dict
    }

Notes:
- Expression matrix loading supports:
  - 10x H5 and MEX if optional dependencies are installed (h5py/scipy)
  - simple CSV/CSV.GZ matrices as a fallback for lightweight/testing usage.

T-989
"""

from __future__ import annotations

import gzip
import json
import logging
import re
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
class _VisiumRoot:
    root: Path
    bin_name: str | None  # e.g. square_002um


@dataclass(frozen=True)
class _FileCandidates:
    positions: Path | None
    expression: Path | None  # file (h5/csv) or directory (MEX)
    json_files: list[Path]


_TRANSCRIPT_REQUIRED_OUT_COLS = ["x", "y", "gene", "cell_id"]
_CELL_REQUIRED_OUT_COLS = ["cell_id", "x", "y", "cell_type"]


def parse_visium_hd(input_dir: str | Path) -> dict[str, Any]:
    """Parse a directory of Visium HD (Space Ranger) outputs.

    Requires the optional dependency ``pandas``.
    """

    if pd is None:  # pragma: no cover
        raise ImportError(
            "parse_visium_hd requires the optional dependency 'pandas'. "
            "Install pandas to use native format parsers."
        )

    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"Visium HD input_dir does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Visium HD input_dir is not a directory: {base}")

    vis_root = _discover_visium_root(base)
    candidates = _discover_files(vis_root.root)

    transcript_df = _empty_transcript_df()
    cell_df = _empty_cell_metadata_df()
    expr_df = pd.DataFrame()

    if candidates.positions is None:
        logger.warning("Visium HD: tissue positions file not found under %s", vis_root.root)
    else:
        cell_df = _load_positions_as_cell_metadata(candidates.positions)

    if candidates.expression is None:
        logger.warning("Visium HD: expression matrix not found under %s", vis_root.root)
    else:
        expr_df = _load_expression_matrix(candidates.expression)

    metadata = _load_metadata_json(candidates.json_files)
    metadata.setdefault("input_dir", str(base))
    metadata.setdefault("selected_root", str(vis_root.root))
    if vis_root.bin_name is not None:
        metadata.setdefault("bin", vis_root.bin_name)

    metadata.setdefault(
        "files",
        {
            "positions": str(candidates.positions) if candidates.positions else None,
            "expression": str(candidates.expression) if candidates.expression else None,
            "json": [str(p) for p in candidates.json_files],
        },
    )

    _validate_transcripts(transcript_df)
    _validate_cell_metadata(cell_df)
    _validate_expression(expr_df)

    return {
        "platform": "visium_hd",
        "transcript_data": transcript_df,
        "cell_metadata": cell_df,
        "expression_matrix": expr_df,
        "metadata": metadata,
    }


def _discover_visium_root(base: Path) -> _VisiumRoot:
    """Pick the most appropriate root directory for Visium HD.

    If ``binned_outputs`` exists, select the smallest bin (highest resolution).
    Otherwise, use ``base``.
    """

    binned = base / "binned_outputs"
    if not binned.exists() or not binned.is_dir():
        return _VisiumRoot(root=base, bin_name=None)

    bins = [d for d in binned.iterdir() if d.is_dir()]
    if not bins:
        return _VisiumRoot(root=base, bin_name=None)

    # Typical bin folder names: square_002um, square_008um, etc.
    # We choose the smallest micron value if parseable.
    def bin_size_um(p: Path) -> float | None:
        m = re.search(r"(\d+)(?:\s*)um", p.name.lower())
        if m:
            return float(m.group(1))
        m2 = re.search(r"(\d+)", p.name)
        if m2:
            # fallback numeric
            return float(m2.group(1))
        return None

    scored: list[tuple[float, Path]] = []
    unscored: list[Path] = []
    for d in bins:
        s = bin_size_um(d)
        if s is None:
            unscored.append(d)
        else:
            scored.append((s, d))

    if scored:
        scored.sort(key=lambda t: t[0])
        chosen = scored[0][1]
        return _VisiumRoot(root=chosen, bin_name=chosen.name)

    # If names are unparseable, choose lexicographically for determinism.
    unscored.sort(key=lambda p: p.name)
    return _VisiumRoot(root=unscored[0], bin_name=unscored[0].name)


def _discover_files(root: Path) -> _FileCandidates:
    # Positions are typically under spatial/
    spatial = root / "spatial"
    positions: Path | None = None
    if spatial.exists() and spatial.is_dir():
        positions = _first_existing(
            [
                spatial / "tissue_positions.csv",
                spatial / "tissue_positions_list.csv",
                spatial / "tissue_positions.parquet",
                spatial / "tissue_positions_list.parquet",
            ]
        )

    # Expression can be an H5 file or a MEX directory. Prefer filtered.
    expression: Path | None = None

    for name in (
        "filtered_feature_bc_matrix.h5",
        "filtered_feature_bc_matrix.H5",
        "raw_feature_bc_matrix.h5",
        "raw_feature_bc_matrix.H5",
    ):
        p = root / name
        if p.exists():
            expression = p
            break

    if expression is None:
        for name in (
            "filtered_feature_bc_matrix",
            "raw_feature_bc_matrix",
        ):
            d = root / name
            if d.exists() and d.is_dir():
                expression = d
                break

    # Lightweight fallback: allow CSV matrices (useful for small exports/tests)
    if expression is None:
        expression = _first_existing(
            [
                root / "expression.csv",
                root / "expression.csv.gz",
                root / "matrix.csv",
                root / "matrix.csv.gz",
                root / "expression.tsv",
            ]
        )

    json_files = sorted(list(root.glob("*.json")) + list(root.glob("*.JSON")))

    return _FileCandidates(positions=positions, expression=expression, json_files=json_files)


def _empty_transcript_df() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in _TRANSCRIPT_REQUIRED_OUT_COLS})


def _empty_cell_metadata_df() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in _CELL_REQUIRED_OUT_COLS})


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


def _coerce_numeric(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _load_positions_as_cell_metadata(path: Path) -> pd.DataFrame:
    suf = "".join(path.suffixes).lower()

    if suf.endswith(".parquet"):
        try:
            df = pd.read_parquet(path)
        except Exception as e:  # pragma: no cover
            raise ValueError(
                "Visium HD: failed reading tissue positions parquet. "
                "Install a parquet engine (pyarrow/fastparquet) or export CSV instead. "
                f"(file: {path}): {e}"
            ) from e
    else:
        try:
            df = pd.read_csv(path)
        except Exception as e:  # pragma: no cover
            raise ValueError(f"Visium HD: failed reading tissue positions CSV: {path}: {e}") from e

    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    # Space Ranger tissue_positions*.csv is typically:
    # barcode,in_tissue,array_row,array_col,pxl_row_in_fullres,pxl_col_in_fullres
    barcode_col = _first_present(colmap, ["barcode", "barcodes", "spot", "spot_id", "cell_id"])
    in_tissue_col = _first_present(colmap, ["in_tissue", "tissue"])  # optional

    px_row_col = _first_present(colmap, ["pxl_row_in_fullres", "pixel_row", "pxl_row", "row_px"])
    px_col_col = _first_present(colmap, ["pxl_col_in_fullres", "pixel_col", "pxl_col", "col_px"])

    array_row_col = _first_present(colmap, ["array_row", "row", "grid_row"])
    array_col_col = _first_present(colmap, ["array_col", "col", "grid_col"])

    if barcode_col is None:
        raise ValueError(
            "Visium HD: tissue positions missing required barcode column. "
            f"Found columns: {list(df.columns)} (file: {path})"
        )

    # Prefer pixel coordinates; otherwise fall back to array coordinates.
    x_src = px_col_col or array_col_col
    y_src = px_row_col or array_row_col

    if x_src is None or y_src is None:
        raise ValueError(
            "Visium HD: tissue positions missing required coordinate columns. "
            "Need pixel (pxl_*_in_fullres) or array (array_row/array_col). "
            f"Found columns: {list(df.columns)} (file: {path})"
        )

    out = pd.DataFrame(
        {
            "cell_id": df[barcode_col].astype("string"),
            "x": df[x_src],
            "y": df[y_src],
            "cell_type": pd.NA,
        }
    )
    out = _coerce_numeric(out, ["x", "y"])
    out["cell_type"] = out["cell_type"].astype("string")

    if in_tissue_col is not None:
        # Keep only in-tissue bins/spots if column exists and is parsable.
        it = pd.to_numeric(df[in_tissue_col], errors="coerce")
        if it.notna().any():
            before = len(out)
            out = out.loc[it.fillna(0).astype(int) == 1].reset_index(drop=True)
            after = len(out)
            if after != before:
                logger.info("Visium HD: filtered to in_tissue==1 (%s -> %s rows)", before, after)

    if out[["x", "y"]].isna().any().any():
        n = int(out[["x", "y"]].isna().any(axis=1).sum())
        logger.warning("Visium HD: %s positions rows have NaN coordinates (%s)", n, path.name)

    return out


def _load_expression_matrix(path: Path) -> pd.DataFrame:
    if path.is_dir():
        return _load_mex_dir(path)

    suf = "".join(path.suffixes).lower()
    if suf.endswith(".h5"):
        return _load_10x_h5(path)

    # CSV/TSV fallback.
    return _load_expression_table_csv(path)


def _load_expression_table_csv(path: Path) -> pd.DataFrame:
    # Supports .csv, .csv.gz, .tsv (tab-separated).
    suf = "".join(path.suffixes).lower()
    try:
        if suf.endswith(".csv.gz"):
            df = pd.read_csv(path, compression="gzip")
        elif suf.endswith(".tsv"):
            df = pd.read_csv(path, sep="\t")
        else:
            df = pd.read_csv(path)
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Visium HD: failed reading expression matrix table: {path}: {e}") from e

    df = _standardize_columns(df)
    colmap = _lower_map_columns(df)

    cell_col = _first_present(colmap, ["cell_id", "barcode", "barcodes", "spot", "spot_id"])
    gene_col = _first_present(colmap, ["gene", "feature", "feature_name", "symbol"])
    count_col = _first_present(colmap, ["count", "counts", "umi", "umis", "value", "expr"])

    # Long format detection.
    if cell_col is not None and gene_col is not None and count_col is not None and len(df.columns) <= 6:
        long = df[[cell_col, gene_col, count_col]].copy()
        long.columns = ["cell_id", "gene", "count"]
        long["cell_id"] = long["cell_id"].astype("string")
        long["gene"] = long["gene"].astype("string")
        long["count"] = pd.to_numeric(long["count"], errors="coerce")
        expr = long.pivot_table(index="cell_id", columns="gene", values="count", aggfunc="sum", fill_value=0)
        return expr

    # Wide format.
    if df.shape[1] < 2:
        raise ValueError(f"Visium HD: expression matrix has too few columns: {path}")

    first = str(df.columns[0]).strip().lower()
    if first in {"cell_id", "barcode", "barcodes", "spot", "spot_id"}:
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
    logger.warning("Visium HD: expression matrix format ambiguous; assumed first column is index (%s)", path.name)
    return expr


def _load_10x_h5(path: Path) -> pd.DataFrame:
    # Same dependency expectations as xenium.py; kept local to avoid importing
    # a hyphenated project package.
    try:
        import h5py  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ValueError(
            "Visium HD: reading feature_bc_matrix.h5 requires the optional dependency 'h5py'. "
            f"Install h5py or provide a CSV expression matrix instead. (file: {path})"
        ) from e

    try:
        import scipy.sparse  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ValueError(
            "Visium HD: reading feature_bc_matrix.h5 requires the optional dependency 'scipy'. "
            f"Install scipy or provide a CSV expression matrix instead. (file: {path})"
        ) from e

    try:
        with h5py.File(path, "r") as f:
            # Space Ranger H5 uses the same /matrix layout as Cell Ranger.
            if "matrix" not in f:
                raise ValueError(f"Visium HD: H5 missing /matrix group: {path}")
            g = f["matrix"]

            data = g["data"][:]
            indices = g["indices"][:]
            indptr = g["indptr"][:]
            shape = tuple(g["shape"][:])

            feat_g = g.get("features")
            if feat_g is None:
                raise ValueError(f"Visium HD: H5 missing /matrix/features: {path}")

            if "name" in feat_g:
                feature_names = feat_g["name"][:]
            elif "feature_name" in feat_g:
                feature_names = feat_g["feature_name"][:]
            else:
                k0 = list(feat_g.keys())[0]
                feature_names = feat_g[k0][:]

            barcodes = g["barcodes"][:]

    except ValueError:
        raise
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Visium HD: failed reading H5 matrix {path}: {e}") from e

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

    mat = scipy.sparse.csc_matrix((data, indices, indptr), shape=shape)
    mat_csr = mat.T.tocsr()
    expr = pd.DataFrame.sparse.from_spmatrix(
        mat_csr,
        index=pd.Index(cells, name="cell_id"),
        columns=pd.Index(genes, name="gene"),
    )
    return expr


def _load_mex_dir(path: Path) -> pd.DataFrame:
    try:
        import scipy.io  # type: ignore
        import scipy.sparse  # type: ignore
    except Exception as e:  # pragma: no cover
        raise ValueError(
            "Visium HD: reading a feature_bc_matrix/ MEX directory requires the optional dependency 'scipy'. "
            f"Install scipy or provide a CSV expression matrix instead. (dir: {path})"
        ) from e

    matrix_path = _first_existing([path / "matrix.mtx.gz", path / "matrix.mtx"])
    barcodes_path = _first_existing([path / "barcodes.tsv.gz", path / "barcodes.tsv"])
    features_path = _first_existing([path / "features.tsv.gz", path / "features.tsv", path / "genes.tsv.gz", path / "genes.tsv"])

    if matrix_path is None or barcodes_path is None or features_path is None:
        raise ValueError(
            "Visium HD: MEX directory missing required files. "
            f"Need matrix.mtx(.gz), barcodes.tsv(.gz), features.tsv(.gz). (dir: {path})"
        )

    try:
        mat = scipy.io.mmread(str(matrix_path))
        mat = mat.tocsc()
    except Exception as e:  # pragma: no cover
        raise ValueError(f"Visium HD: failed reading MEX matrix {matrix_path}: {e}") from e

    barcodes = _read_tsv_first_col(barcodes_path)
    features = _read_tsv_first_col(features_path, prefer_second_col=True)

    mat_csr = mat.T.tocsr()
    expr = pd.DataFrame.sparse.from_spmatrix(
        mat_csr,
        index=pd.Index(barcodes, name="cell_id"),
        columns=pd.Index(features, name="gene"),
    )
    return expr


def _read_tsv_first_col(path: Path, prefer_second_col: bool = False) -> list[str]:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:  # type: ignore[arg-type]
        rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]

    if not rows:
        return []

    if prefer_second_col and len(rows[0]) >= 2:
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
            logger.warning("Visium HD: failed reading JSON metadata %s: %s", p, e)

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
            raise ValueError(f"Visium HD: transcript_data missing required column: {c}")


def _validate_cell_metadata(df: pd.DataFrame) -> None:
    for c in _CELL_REQUIRED_OUT_COLS:
        if c not in df.columns:
            raise ValueError(f"Visium HD: cell_metadata missing required column: {c}")

    if len(df) == 0:
        return

    if df["cell_id"].isna().any():
        n = int(df["cell_id"].isna().sum())
        logger.warning("Visium HD: cell_metadata has %s rows with missing cell_id", n)


def _validate_expression(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return

    if df.index.isna().any():
        logger.warning("Visium HD: expression_matrix has missing index (cell_id)")

    n_nans = int(df.isna().sum().sum())
    if n_nans:
        logger.warning("Visium HD: expression_matrix contains %s NaN values", n_nans)
