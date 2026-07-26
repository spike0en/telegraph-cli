"""
Telegra.ph API Management Package

@brief Top-level package initialization module.
"""

from .manager import TelegraphManager, TelegraphAPIError
from .cli import main

__all__ = ['TelegraphManager', 'TelegraphAPIError', 'main']
__version__ = '1.0.0'
