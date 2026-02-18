import subprocess
import sys
import unittest


class TestParsersLazyImports(unittest.TestCase):
    def test_import_parsers_does_not_require_pandas(self):
        """`import parsers` should not eagerly import optional deps like pandas.

        We install an import hook that *fails* any attempt to import pandas.
        The package import should still succeed because parsers are loaded lazily.
        """

        code = r"""
import importlib.abc
import importlib.util
import sys

class BlockPandas(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'pandas' or fullname.startswith('pandas.'):
            raise ImportError('blocked pandas import (test)')
        return None

sys.meta_path.insert(0, BlockPandas())

import parsers

# Accessing parsers package itself should not trigger pandas.
print('ok')
"""

        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            self.fail(f"subprocess failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        self.assertIn("ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
