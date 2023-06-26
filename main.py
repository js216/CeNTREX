import argparse
import logging
import sys
from pathlib import Path

import PyQt5.QtWidgets as qt
from rich.logging import RichHandler

from gui import CentrexGUI

# fancy colors and formatting for logging
FORMAT = "%(message)s"
logging.basicConfig(
    level="WARNING",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)

filepath = Path(__file__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CeNTREX data acquisition")
    parser.add_argument(
        "--settings",
        required=False,
        help="path to settings file",
        action="store",
    )
    parser.add_argument("-r", required=False, help="relative path", action="store_true")

    parser.add_argument(
        "-start", required=False, help="auto-start acquisition", action="store_true"
    )

    parser.add_argument(
        "-clear", required=False, help="clear hdf file write flag", action="store_true"
    )

    parser.add_argument(
        "-mandatory_parameters",
        required=False,
        help="popup mandatory parameters",
        action="store_true",
    )

    arguments = parser.parse_args()

    if arguments.settings is None:
        settings_path = filepath.parent / "config" / "settings.ini"
    else:
        settings_path = Path(arguments.settings)
        if arguments.r:
            settings_path = Path().cwd() / settings_path

    if not settings_path.is_file():
        logging.error(f"Settings file {settings_path} does not exist.")
    else:
        app = qt.QApplication([])
        main_window = CentrexGUI(
            app,
            settings_path=settings_path,
            auto_start=arguments.start,
            clear=arguments.clear,
            mandatory_parameters=arguments.mandatory_parameters,
        )
        sys.exit(app.exec_())
