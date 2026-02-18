import tempfile
import unittest
from pathlib import Path

import sys

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None

# Allow running tests from repo root without installing as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsers.universal import detect_spatial_format, load_spatial


class TestVisiumHDParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if pd is None:
            raise unittest.SkipTest("pandas not installed")
    def _write_minimal_visium_hd(self, base: Path) -> Path:
        """Create a minimal Visium HD-like directory using CSV fallbacks.

        Structure:
          base/
            binned_outputs/
              square_002um/
                spatial/tissue_positions_list.csv
                expression.csv  (long format: cell_id,gene,count)
        """

        root = base / "binned_outputs" / "square_002um"
        (root / "spatial").mkdir(parents=True)

        # Space Ranger tissue_positions_list.csv columns.
        pos = pd.DataFrame(
            {
                "barcode": ["AA", "BB", "CC"],
                "in_tissue": [1, 0, 1],
                "array_row": [0, 0, 1],
                "array_col": [0, 1, 0],
                "pxl_row_in_fullres": [100.0, 200.0, 300.0],
                "pxl_col_in_fullres": [10.0, 20.0, 30.0],
            }
        )
        pos.to_csv(root / "spatial" / "tissue_positions_list.csv", index=False)

        expr_long = pd.DataFrame(
            {
                "cell_id": ["AA", "AA", "CC"],
                "gene": ["G1", "G2", "G1"],
                "count": [5, 1, 2],
            }
        )
        expr_long.to_csv(root / "expression.csv", index=False)

        return base

    def test_parse_visium_hd_minimal(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write_minimal_visium_hd(base)

            from parsers.visium_hd import parse_visium_hd

            out = parse_visium_hd(base)
            self.assertEqual(out["platform"], "visium_hd")

            tx = out["transcript_data"]
            self.assertListEqual(list(tx.columns), ["x", "y", "gene", "cell_id"])
            self.assertEqual(len(tx), 0)

            cells = out["cell_metadata"]
            self.assertListEqual(list(cells.columns), ["cell_id", "x", "y", "cell_type"])
            # in_tissue=0 row should be filtered out
            self.assertEqual(set(cells["cell_id"].tolist()), {"AA", "CC"})

            expr = out["expression_matrix"]
            self.assertEqual(expr.index.name, "cell_id")
            self.assertIn("G1", expr.columns)
            self.assertEqual(set(expr.index.tolist()), {"AA", "CC"})

    def test_universal_detection_and_loading_visium_hd(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self._write_minimal_visium_hd(base)

            det = detect_spatial_format(base)
            self.assertEqual(det.platform, "visium_hd")

            out = load_spatial(base)
            self.assertEqual(out["platform"], "visium_hd")


if __name__ == "__main__":
    unittest.main()
