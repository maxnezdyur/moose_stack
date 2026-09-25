"""``python -m tool`` is ``python -m tool.cli``."""

import sys

from .cli import main

sys.exit(main())
