"""xpublish_erddap provides an ERDDAP-compatible griddap router for Xpublish."""

from xpublish_erddap.plugin import ErddapPlugin

__all__ = ["ErddapPlugin"]

try:
    from ._version import __version__
except ImportError:
    __version__ = "unknown"
