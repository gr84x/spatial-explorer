import sys
import unittest
from pathlib import Path


class TestXeniumParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Make parsers/ importable without requiring installation.
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root))

    def test_parse_xenium_sample_directory(self):
        try:
            import pandas as pd  # noqa: F401
            import h5py  # noqa: F401
        except Exception as e:  # pragma: no cover
            self.skipTest(f"required dependency not installed: {e}")

        from parsers.xenium import parse_xenium

        # This repo includes a small Xenium example directory for development.
        sample_dir = Path(__file__).resolve().parents[3] / "xenium-analysis"
        if not sample_dir.exists():
            self.skipTest(f"sample dataset not found: {sample_dir}")

        res = parse_xenium(sample_dir)
        self.assertEqual(res["platform"], "xenium")

        tx = res["transcript_data"]
        cells = res["cell_metadata"]
        expr = res["expression_matrix"]

        self.assertGreater(len(tx), 0)
        self.assertTrue({"x", "y", "gene", "cell_id"}.issubset(set(tx.columns)))

        self.assertGreater(len(cells), 0)
        self.assertTrue({"cell_id", "x", "y", "cell_type"}.issubset(set(cells.columns)))

        # Expression matrix should load from the included H5 in the sample directory.
        self.assertIsNotNone(expr)
        self.assertFalse(expr.empty)
        self.assertEqual(expr.shape[0], len(cells))
        self.assertIsNotNone(expr.index.name)
        self.assertGreater(expr.shape[1], 0)

        # Spot-check that counts are numeric.
        v = expr.iloc[0, 0]
        self.assertTrue(isinstance(v, (int, float)) or getattr(v, "__float__", None) is not None)


if __name__ == "__main__":
    unittest.main()
