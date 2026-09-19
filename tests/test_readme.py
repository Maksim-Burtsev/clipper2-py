"""Every ```python block in README.md and docs/guide.md runs and prints what it claims.

The blocks of one page share a namespace and run in the order they appear, the way the page
is read.  A `# -> ...` comment is one expected line of output, in order.
"""

import contextlib
import io
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("page", ["README.md", "docs/guide.md"])
def test_python_blocks_run_and_print_what_they_claim(page):
    blocks = re.findall(r"^```python\n(.*?)^```", (ROOT / page).read_text(encoding="utf-8"), re.S | re.M)
    assert len(blocks) >= 4, f"no python blocks found in {page}"
    namespace: dict = {}
    for number, block in enumerate(blocks, 1):
        expected = [line.split("# ->", 1)[1].strip() for line in block.splitlines() if "# ->" in line]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exec(compile(block, f"{page} block {number}", "exec"), namespace)
        printed = [line.rstrip() for line in stdout.getvalue().splitlines()]
        assert printed == expected, f"{page} block {number}:\n{block}"
