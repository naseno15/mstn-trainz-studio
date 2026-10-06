"""python -m trainz_studio.lib.im_editor [path.im]  — UI;  … --cli …"""
from __future__ import annotations

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "--cli":
        from .cli import main as cli_main

        cli_main(argv[1:])
        return
    if argv and argv[0] in ("selfcheck", "--selfcheck"):
        from .core import selfcheck

        print(selfcheck())
        return
    # When run as python -m im_editor, relative import of app works.
    # app.py also runs as script from start.sh via path hack.
    from .app import main as ui_main

    ui_main(argv)


if __name__ == "__main__":
    main()
