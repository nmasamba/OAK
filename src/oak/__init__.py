# SPDX-License-Identifier: Apache-2.0
"""OAK Community control-plane package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("oak-community")
except PackageNotFoundError:  # pragma: no cover - editable installs provide metadata
    __version__ = "0+unknown"

__all__ = ["__version__"]
