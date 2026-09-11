"""Feather's public handoff command (Python 3.11+, standard library only)."""
import json
import sys

sys.dont_write_bytecode = True

if sys.version_info < (3, 11):
    print(json.dumps({"status": "error", "code": "python-version",
                      "message": "Python 3.11+ required. Ask whether to help install it."}))
    sys.exit(2)

from feather_handoff.cli import main

if __name__ == "__main__":
    sys.exit(main())
