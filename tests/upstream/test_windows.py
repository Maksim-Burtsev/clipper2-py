"""Port of third_party/Clipper2/CPP/Tests/TestWindows.cpp — nothing to port.

The whole file is `#ifdef WIN32 #include <Windows.h> #include "clipper2/clipper.h" #endif`
(see https://github.com/AngusJohnson/Clipper2/issues/601): it checks that the headers still
compile after Windows.h has defined its macros. It declares no TEST and has no Python
equivalent.
"""

import pytest

pytest.skip(
    "TestWindows.cpp only checks that the C++ headers compile after Windows.h — no TESTs",
    allow_module_level=True,
)
