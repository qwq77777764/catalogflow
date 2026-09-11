"""Allow `python -m catalogflow` to work when console scripts are not on PATH."""

from .cli import main

raise SystemExit(main())
