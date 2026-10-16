"""Auto-import every ``*_tool.py`` module so their ``@tool`` decorators run.

Each import is wrapped in try/except: a module that fails to import (e.g. a
missing optional dependency like ``duckduckgo-search``) is skipped with a
warning instead of taking down the whole registry.
"""

import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)

for _module in pkgutil.iter_modules(__path__):
    if _module.name.endswith("_tool"):
        try:
            importlib.import_module(f"{__name__}.{_module.name}")
        except Exception as e:  # optional dep missing, bad module, etc.
            logger.warning("Skipping tool module %s: %s", _module.name, e)
