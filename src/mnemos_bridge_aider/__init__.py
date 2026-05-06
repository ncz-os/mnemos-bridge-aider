"""Aider integration package for MNEMOS bridge."""

from .adapter import MnemosAiderAdapter, register_with_aider
from .cli import main

__all__ = ["MnemosAiderAdapter", "main", "register_with_aider"]

__version__ = "0.2.0"
