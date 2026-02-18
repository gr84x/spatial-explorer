import json
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


class TestMerscopeParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if pd is None:
            raise unittest.SkipTest("pandas not installed")
    def test_parse_merscope_minimal(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)

            # detected_transcripts.csv
            tx = pd.DataFrame(
                {
                    "global_x": [1.0, 2.0, 3.0],
                    "global_y": [10.0, 20.0, 30.0],
                    "gene": ["A", "B", "C"],
                    "EntityID": [1, -1, 2],
                }
            )
            tx.to_csv(base / "detected_transcripts.csv", index=False)

            # cell metadata
            cells = pd.DataFrame(
                {
                    "EntityID": [1, 2],
                    "center_x": [1.5, 3.5],
                    "center_y": [11.5, 31.5],
                }
            )
            cells.to_csv(base / "cell_metadata.csv", index=False)

            # expression matrix
            expr = pd.DataFrame(
                {
                    "EntityID": [1, 2],
                    "A": [5, 0],
                    "B": [0, 7],
                }
            )
            expr.to_csv(base / "cell_by_gene.csv", index=False)

            (base / "experiment.json").write_text(json.dumps({"foo": "bar"}))

            from parsers.merscope import parse_merscope

            out = parse_merscope(base)
            self.assertEqual(out["platform"], "merscope")

            tdf = out["transcript_data"]
            self.assertListEqual(list(tdf.columns), ["x", "y", "gene", "cell_id"])
            # -1 becomes NA
            self.assertTrue(pd.isna(tdf.loc[1, "cell_id"]))

            cdf = out["cell_metadata"]
            self.assertListEqual(list(cdf.columns), ["cell_id", "x", "y", "cell_type"])
            self.assertEqual(set(cdf["cell_id"].tolist()), {"1", "2"})

            edf = out["expression_matrix"]
            self.assertEqual(edf.index.name, "cell_id")
            self.assertIn("A", edf.columns)

            self.assertIn("experiment.json", out["metadata"])

    def test_parse_merscope_nested_region_dir(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            region = base / "region_0" / "analysis_outputs"
            region.mkdir(parents=True)

            pd.DataFrame(
                {"global_x": [1.0], "global_y": [2.0], "gene": ["A"], "EntityID": [1]}
            ).to_csv(region / "detected_transcripts.csv", index=False)
            pd.DataFrame({"EntityID": [1], "A": [1]}).to_csv(region / "cell_by_gene.csv", index=False)

            # Parsing should succeed even when pointed at a higher-level dir.
            from parsers.merscope import parse_merscope

            out = parse_merscope(base)
            self.assertEqual(out["platform"], "merscope")
            self.assertEqual(len(out["transcript_data"]), 1)

            det = detect_spatial_format(base)
            self.assertEqual(det.platform, "merscope")

    def test_universal_detection_and_loading(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            pd.DataFrame({"global_x": [1.0], "global_y": [2.0], "gene": ["A"]}).to_csv(
                base / "detected_transcripts.csv", index=False
            )
            pd.DataFrame({"EntityID": [1], "A": [1]}).to_csv(base / "cell_by_gene.csv", index=False)

            det = detect_spatial_format(base)
            self.assertEqual(det.platform, "merscope")

            out = load_spatial(base)
            self.assertEqual(out["platform"], "merscope")


if __name__ == "__main__":
    unittest.main()
