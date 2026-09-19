"""Every ```python block in README.md runs, and prints what its `# ->` comments say.

The blocks share one namespace and run in the order they appear, the way the README is
read.  A `# -> ...` comment is one expected line of output, in order.
"""

import contextlib
import io
import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"
BLOCKS = re.findall(r"^```python\n(.*?)^```", README.read_text(encoding="utf-8"), re.S | re.M)


def test_readme_blocks_run_and_print_what_they_claim():
    assert len(BLOCKS) > 5, "no python blocks found in README.md"
    namespace: dict = {}
    for number, block in enumerate(BLOCKS, 1):
        expected = [line.split("# ->", 1)[1].strip() for line in block.splitlines() if "# ->" in line]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exec(compile(block, f"README.md block {number}", "exec"), namespace)
        printed = [line.rstrip() for line in stdout.getvalue().splitlines()]
        assert printed == expected, f"block {number}:\n{block}"
