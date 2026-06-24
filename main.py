#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Convenience entry point: `python cli/main.py ...` without installing the package.

`hector` lives in this same directory, so we put it on sys.path explicitly rather
than relying on the interpreter having added the script's directory (which only
happens when the script is invoked *from* this folder — copy or symlink it
elsewhere and a bare `import hector` would otherwise fail with ModuleNotFound).
The installed `hector` console script (see setup.py) does not need this.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hector.pipeline import main

if __name__ == "__main__":
    main()
