"""The project's own checks as a unittest suite, for tools that look for tests/: python3 -m unittest discover tests

The tests themselves live next to the code (selfcheck() in each module, the benchmark, the docs check), which is what
CI runs; this only runs them. Stdlib only, no AI calls (server.py --check turns the AI off).
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=600)


class Checks(unittest.TestCase):
    def check(self, *args):
        r = run(*args)
        self.assertEqual(r.returncode, 0, f"{' '.join(args)} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")

    def test_selfchecks(self):  # memory, recall, auth, MCP (every tool and its four hints), hand-off
        self.check("server.py", "--check")

    def test_benchmark(self):  # understanding, recall and secret redaction gates
        self.check("bench.py")

    def test_docs(self):  # docs up to date, links resolve, every MCP tool documented
        self.check("docs_site.py", "--check")


if __name__ == "__main__":
    unittest.main()
