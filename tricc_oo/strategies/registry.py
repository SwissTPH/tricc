"""
Lightweight strategy registry for TRICC input and output strategies.

This module provides a simple, explicit registration mechanism for strategies
instead of relying on fragile globals() lookups.

Usage:

    from tricc_oo.strategies.registry import (
        register_input_strategy,
        register_output_strategy,
        get_input_strategy,
        get_output_strategy,
    )

    @register_input_strategy("MyCoolStrategy")
    class MyCoolStrategy(BaseInputStrategy):
        ...

    strategy_cls = get_input_strategy("MyCoolStrategy")
    # or pass the class directly (useful in tests / advanced usage)
    strategy_cls = get_input_strategy(MyCoolStrategy)
"""

from __future__ import annotations

import logging
from typing import Dict, Type, Union, overload

logger = logging.getLogger("default")

# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

# Maps registered name -> strategy class
INPUT_STRATEGIES: Dict[str, Type] = {}
OUTPUT_STRATEGIES: Dict[str, Type] = {}


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def register_input_strategy(name: str):
    """
    Decorator to register an input strategy under a stable name.

    Example:
        @register_input_strategy("YamlStrategy")
        class YamlStrategy(BaseInputStrategy):
            ...
    """
    def decorator(cls: Type) -> Type:
        if name in INPUT_STRATEGIES and INPUT_STRATEGIES[name] is not cls:
            logger.warning(
                f"Input strategy name '{name}' is already registered to "
                f"{INPUT_STRATEGIES[name]}. Overwriting with {cls}."
            )
        INPUT_STRATEGIES[name] = cls
        # Also allow lookup by the class itself (for direct usage)
        INPUT_STRATEGIES.setdefault(cls.__name__, cls)
        return cls

    return decorator


def register_output_strategy(name: str):
    """
    Decorator to register an output strategy under a stable name.

    Example:
        @register_output_strategy("OpenSRPStrategy")
        class OpenSRPStrategy(FHIRStrategy):
            ...
    """
    def decorator(cls: Type) -> Type:
        if name in OUTPUT_STRATEGIES and OUTPUT_STRATEGIES[name] is not cls:
            logger.warning(
                f"Output strategy name '{name}' is already registered to "
                f"{OUTPUT_STRATEGIES[name]}. Overwriting with {cls}."
            )
        OUTPUT_STRATEGIES[name] = cls
        OUTPUT_STRATEGIES.setdefault(cls.__name__, cls)
        return cls

    return decorator


# ---------------------------------------------------------------------------
# Lookup functions (with direct class passthrough)
# ---------------------------------------------------------------------------

@overload
def get_input_strategy(name_or_cls: str) -> Type: ...
@overload
def get_input_strategy(name_or_cls: Type) -> Type: ...

def get_input_strategy(name_or_cls: Union[str, Type]) -> Type:
    """
    Resolve an input strategy by registered name or by passing the class directly.

    This is the recommended way to obtain strategy classes throughout the codebase
    and in the CLI.
    """
    if isinstance(name_or_cls, type):
        # Direct class usage (very useful for tests and programmatic calls)
        return name_or_cls

    if not isinstance(name_or_cls, str):
        raise TypeError(
            f"get_input_strategy expects a string name or a strategy class, "
            f"got {type(name_or_cls)}"
        )

    # Try exact registered name first
    if name_or_cls in INPUT_STRATEGIES:
        return INPUT_STRATEGIES[name_or_cls]

    # Fallback: try class name (for convenience when people use the Python class name)
    if name_or_cls in INPUT_STRATEGIES:
        return INPUT_STRATEGIES[name_or_cls]

    available = sorted(set(INPUT_STRATEGIES.keys()))
    raise ValueError(
        f"Unknown input strategy '{name_or_cls}'. "
        f"Available strategies: {', '.join(available)}"
    )


@overload
def get_output_strategy(name_or_cls: str) -> Type: ...
@overload
def get_output_strategy(name_or_cls: Type) -> Type: ...

def get_output_strategy(name_or_cls: Union[str, Type]) -> Type:
    """
    Resolve an output strategy by registered name or by passing the class directly.
    """
    if isinstance(name_or_cls, type):
        return name_or_cls

    if not isinstance(name_or_cls, str):
        raise TypeError(
            f"get_output_strategy expects a string name or a strategy class, "
            f"got {type(name_or_cls)}"
        )

    if name_or_cls in OUTPUT_STRATEGIES:
        return OUTPUT_STRATEGIES[name_or_cls]

    if name_or_cls in OUTPUT_STRATEGIES:
        return OUTPUT_STRATEGIES[name_or_cls]

    available = sorted(set(OUTPUT_STRATEGIES.keys()))
    raise ValueError(
        f"Unknown output strategy '{name_or_cls}'. "
        f"Available strategies: {', '.join(available)}"
    )


def list_input_strategies() -> Dict[str, Type]:
    """Return a copy of the registered input strategies (for help text, debugging, etc.)."""
    return dict(INPUT_STRATEGIES)


def list_output_strategies() -> Dict[str, Type]:
    """Return a copy of the registered output strategies."""
    return dict(OUTPUT_STRATEGIES)
