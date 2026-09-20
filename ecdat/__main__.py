"""Allow `python -m ecdat` to run the CLI."""

from ecdat.cli import main

raise SystemExit(main())