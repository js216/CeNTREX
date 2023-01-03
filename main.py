import logging
import sys

import PyQt5.QtWidgets as qt
from rich.logging import RichHandler

from gui import CentrexGUI

# fancy colors and formatting for logging
FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET",
    format=FORMAT,
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)

if __name__ == "__main__":
    app = qt.QApplication(sys.argv)
    main_window = CentrexGUI(app)
    sys.exit(app.exec_())
