#!/usr/bin/env python3
"""
Telegra.ph CLI Root Entrypoint Launcher

Responsibility:
    Top-level executable entry point (`python telegraph.py <command>`) for running the
    Telegraph CLI tool from the root directory. Dispatches execution to `telegraph_api.cli.main()`.
"""

import sys
from pathlib import Path

# Inject project root directory into Python sys.path
sys.path.insert(0, str(Path(__file__).parent))

from telegraph_api.cli import main

if __name__ == '__main__':
    main()
