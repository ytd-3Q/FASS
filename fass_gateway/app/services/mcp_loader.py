from __future__ import annotations

import importlib
import pkgutil


def load_builtin_tools() -> None:
    from .. import mcp_tools

    for m in pkgutil.iter_modules(mcp_tools.__path__, mcp_tools.__name__ + "."):
        importlib.import_module(m.name)

