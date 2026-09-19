"""Python bindings for the Clipper2 polygon clipping and offsetting library."""

from ._clipper2 import *  # noqa: F401,F403
from ._clipper2 import CLIPPER2_VERSION  # noqa: F401

from importlib.metadata import version as _version

from . import z  # noqa: E402,F401

__version__ = _version("clipper2-py")
