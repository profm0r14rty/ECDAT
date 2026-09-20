"""ECDAT — Enterprise Cryptographic Discovery & Analysis Tool."""

import importlib.metadata

DIST_NAME = "ecdat"

try:
    __version__ = importlib.metadata.version(DIST_NAME)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0+unknown"