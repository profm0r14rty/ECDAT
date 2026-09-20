"""ECDAT CLI — entry point and command dispatch."""

import sys


def main(argv=None):
    """CLI entry point. Returns exit code (int)."""
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 1 and argv[0] == "--version":
        from ecdat import __version__

        print(f"ecdat {__version__}")
        return 0

    # Placeholder — commands land in the next task.
    print("ecdat: commands arrive in the next task", file=sys.stderr)
    return 2