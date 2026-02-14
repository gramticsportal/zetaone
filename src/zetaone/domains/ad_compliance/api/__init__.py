"""
API request/response handling.

Thin layer that handles HTTP requests and delegates to the pipeline.
"""

from flask import Flask
from .routes import create_app

__all__ = ['create_app']
