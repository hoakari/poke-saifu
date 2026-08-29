"""Entry point for Poke-Saifu Desktop GUI Application."""

import sys

# Tell Windows to treat this as a standalone application so the custom icon appears on the taskbar
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("pokesaifu.battleparser.desktop.v1")
    except Exception:
        pass

from poke_saifu.gui import PokeSaifuApp


def main():
    app = PokeSaifuApp()
    app.mainloop()


if __name__ == "__main__":
    main()
