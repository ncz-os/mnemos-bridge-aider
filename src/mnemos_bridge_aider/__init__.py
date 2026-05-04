"""Aider integration package for MNEMOS bridge."""

from .adapter import MnemosAiderAdapter
from .cli import main

__all__ = ["MnemosAiderAdapter", "main"]

__version__ = "0.1.0"
