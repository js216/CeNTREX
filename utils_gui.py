import logging
from typing import Optional

import PySide6
import PySide6.QtWidgets as qt


def LabelFrame(
    label: str,
    type: str = "grid",
    maxWidth: Optional[float] = None,
    fixed: bool = False,
):
    # make a framed box
    box = qt.QGroupBox(label)

    # box size
    if maxWidth:
        box.setMaximumWidth(maxWidth)

    # select type of layout
    if type == "grid":
        layout = qt.QGridLayout()
    elif type == "hbox":
        layout = qt.QHBoxLayout()
    elif type == "vbox":
        layout = qt.QVBoxLayout()
    box.setLayout(layout)

    if fixed:
        layout.setSizeConstraint(qt.QLayout.SetFixedSize)

    return box, layout


def ScrollableLabelFrame(
    label,
    type="grid",
    fixed=False,
    minWidth=None,
    minHeight=None,
    vert_scroll=True,
    horiz_scroll=True,
):
    # make the outer (framed) box
    outer_box = qt.QGroupBox(label)
    outer_layout = qt.QGridLayout()
    outer_box.setLayout(outer_layout)

    # box size
    if minHeight:
        outer_box.setMinimumHeight(minHeight)
    if minWidth:
        outer_box.setMinimumWidth(minWidth)

    # make the inner grid
    inner_box = qt.QWidget()
    if type == "grid":
        inner_layout = qt.QGridLayout()
    elif type == "flexgrid":
        inner_layout = FlexibleGridLayout()
    elif type == "hbox":
        inner_layout = qt.QHBoxLayout()
    elif type == "vbox":
        inner_layout = qt.QVBoxLayout()
    inner_layout.setContentsMargins(0, 0, 0, 0)
    inner_box.setLayout(inner_layout)

    # make a scrollable area, and add the inner area to it
    sa = qt.QScrollArea()
    if not horiz_scroll:
        sa.setHorizontalScrollBarPolicy(PySide6.QtCore.Qt.ScrollBarAlwaysOff)
    if not vert_scroll:
        sa.setVerticalScrollBarPolicy(PySide6.QtCore.Qt.ScrollBarAlwaysOff)
        sa.setMinimumHeight(
            sa.sizeHint().height() - 40
        )  # the recommended height is too large
    sa.setFrameStyle(16)
    sa.setWidgetResizable(True)
    sa.setWidget(inner_box)

    # add the scrollable area to the outer (framed) box
    outer_layout.addWidget(sa)

    if fixed:
        inner_layout.setSizeConstraint(qt.QLayout.SetFixedSize)

    return outer_box, inner_layout


def message_box(title: str, text: str, message: str = ""):
    msg = qt.QMessageBox()
    msg.setIcon(qt.QMessageBox.Information)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setInformativeText(message)
    msg.exec_()


def error_box(title, text, message=""):
    msg = qt.QMessageBox()
    msg.setIcon(qt.QMessageBox.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setInformativeText(message)
    msg.exec_()


def update_QComboBox(cbx, options, value):
    # update the QComboBox with new runs
    cbx.clear()
    for option in options:
        cbx.addItem(option)

    # select the last run by default
    cbx.setCurrentText(value)


class FlexibleGridLayout(qt.QHBoxLayout):
    """A QHBoxLayout of QVBoxLayouts."""

    def __init__(self):
        super().__init__()
        self.cols = {}

        # populate the grid with placeholders
        for col in range(10):
            self.cols[col] = qt.QVBoxLayout()
            self.addLayout(self.cols[col])

            # add stretchable spacer to prevent stretching the device controls boxes
            self.cols[col].addStretch()

            # reverse the layout order to keep the spacer always at the bottom
            self.cols[col].setDirection(qt.QBoxLayout.BottomToTop)

            # add horizontal placeholders
            vbox = self.cols[col]
            for row in range(10):
                vbox.addLayout(qt.QHBoxLayout())

    def addWidget(self, widget, row: int, col: int):
        vbox = self.cols[col]
        rev_row = vbox.count() - 1 - row
        placeholder = vbox.itemAt(rev_row).layout()
        if not placeholder.itemAt(0):
            placeholder.addWidget(widget)

    def clear(self):
        """Remove all widgets."""
        for col_num, col in self.cols.items():
            for i in reversed(range(col.count())):
                try:
                    if col.itemAt(i).layout():
                        if col.itemAt(i).layout().itemAt(0) is not None:
                            col.itemAt(i).layout().itemAt(0).widget().setParent(None)
                except AttributeError:
                    logging.info(
                        "Exception in clear() in class FlexibleGridLayout",
                        exc_info=True,
                    )
                    pass


def error_popup(message: str):
    err_msg = qt.QMessageBox()
    err_msg.setWindowTitle("Error")
    err_msg.setIcon(qt.QMessageBox.Critical)
    err_msg.setText(message)
    err_msg.setStandardButtons(qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
    err_msg.exec()
