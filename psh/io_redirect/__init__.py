"""I/O redirection package."""
from .fd_remap import remap_fds
from .manager import IOManager

__all__ = ['IOManager', 'remap_fds']
