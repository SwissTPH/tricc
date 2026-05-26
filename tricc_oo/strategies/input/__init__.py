"""
Input strategies for TRICC.

Currently supported:
- DrawioStrategy (default) - reads .drawio XML files
- YamlStrategy - simplified YAML format, primarily for testing
  transformations (inheritance, calculate logic, etc.)
"""

from tricc_oo.strategies.input.drawio import DrawioStrategy
from tricc_oo.strategies.input.yaml import YamlStrategy

__all__ = ["DrawioStrategy", "YamlStrategy"]
