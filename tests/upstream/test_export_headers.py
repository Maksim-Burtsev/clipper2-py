"""Port of third_party/Clipper2/CPP/Tests/TestExportHeaders.cpp — not applicable.

Its four TESTs (ExportHeader64, ExportHeaderD, ExportHeaderTree64, ExportHeaderTreeD)
exercise clipper.export.h, the C ABI for DLL consumers, which is deliberately not bound
(spec decision 11 / DEVIATIONS.md section 9).
"""

import pytest

pytest.skip(
    "clipper.export.h (a C ABI for DLL users) is not bound — spec decision 11",
    allow_module_level=True,
)
