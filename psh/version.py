#!/usr/bin/env python3
"""Version information for Python Shell (psh).

See CHANGELOG.md for detailed version history.
"""

# Semantic versioning: MAJOR.MINOR.PATCH
__version__ = "0.192.1"


def get_version():
    """Return the current version string."""
    return __version__


def get_version_info():
    """Return detailed version information."""
    return f"Python Shell (psh) version {__version__}"
