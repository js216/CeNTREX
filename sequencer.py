import datetime
import itertools
import json
import logging
import os
import threading
import time

import numpy as np
import PyQt5
import PyQt5.QtWidgets as qt
import yaml

from protocols import CentrexGUIProtocol


def parse_dummy_variables(parameter, parent_info: dict):
    if len(parameter) < 2:
        return parameter
    if parameter[:4] == "$dev":
        try:
            parameter = int(parameter.strip("$dev"))
            parameter = parent_info[parameter][0]
        except Exception as e:
            logging.warning(e)
        return parameter
    if parameter[:3] == "$fn":
        try:
            parameter = int(parameter.strip("$fn"))
            parameter = parent_info[parameter][1]
        except Exception as e:
            logging.warning(e)
        return parameter
    elif parameter[0] == "$":
        try:
            parameter = int(parameter.strip("$"))
            parameter = parent_info[parameter][2]
        except Exception as e:
            logging.warning(e)
        return parameter
    else:
        return parameter


class SequencerGUI(qt.QWidget):
    def __init__(self, parent: CentrexGUIProtocol):
        super().__init__()
        self.parent = parent
        self.sequencer = None

        # make a box to contain the sequencer
        self.main_frame = qt.QVBoxLayout()
        self.setLayout(self.main_frame)

        # make the tree
        self.qtw = qt.QTreeWidget()
        self.main_frame.addWidget(self.qtw)
        self.qtw.setColumnCount(6)
        self.qtw.setHeaderLabels(
            ["Device", "Function", "Parameters", "Δt [s]", "Wait?", "Repeat"]
        )
        self.qtw.setAlternatingRowColors(True)
        self.qtw.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
        self.qtw.setDragEnabled(True)
        self.qtw.setAcceptDrops(True)
        self.qtw.setDropIndicatorShown(True)
        self.qtw.setDragDropMode(qt.QAbstractItemView.InternalMove)

        # populate the tree
        self.load_from_file()

        # box for buttons
        self.bbox = qt.QHBoxLayout()
        self.main_frame.addLayout(self.bbox)

        # button to add new item
        pb = qt.QPushButton("Add line")
        pb.clicked[bool].connect(self.add_line)
        self.bbox.addWidget(pb)

        # button to remove currently selected line
        pb = qt.QPushButton("Remove selected line(s)")
        pb.clicked[bool].connect(self.remove_line)
        self.bbox.addWidget(pb)

        # text box to enter the number of repetitions of the entire sequence
        self.repeat_le = qt.QLineEdit("# of repeats")
        sp = qt.QSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Preferred)
        sp.setHorizontalStretch(1)
        self.repeat_le.setSizePolicy(sp)
        self.bbox.addWidget(self.repeat_le)

        # button to loop forever, or not, the entire sequence
        self.loop_pb = qt.QPushButton("Single run")
        self.loop_pb.clicked[bool].connect(self.toggle_loop)
        self.bbox.addWidget(self.loop_pb)

        # button to start/stop the sequence
        self.start_pb = qt.QPushButton("Start")
        self.start_pb.clicked[bool].connect(self.start_sequencer)
        self.bbox.addWidget(self.start_pb)

        self.pause_pb = qt.QPushButton("Pause")
        self.pause_pb.clicked[bool].connect(self.pause_sequencer)
        self.bbox.addWidget(self.pause_pb)

        # progress bar
        self.progress = qt.QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.setMinimum(0)
        self.progress.hide()
        self.bbox.addWidget(self.progress)

        # settings / defaults
        # TODO: use a Config class to do this
        self.circular = False

    def toggle_loop(self):
        if self.circular:
            self.circular = False
            self.loop_pb.setText("Single run")
        else:
            self.circular = True
            self.loop_pb.setText("Looping forever")

    def load_from_file(self):
        # check file exists
        fname = self.parent.config["files"]["sequence_fname"]
        if not os.path.exists(fname):
            logging.warning("Sequencer load warning: file does not exist.")
            return

        # read from file
        with open(fname, "r") as f:
            tree_list = yaml.safe_load(f)

        # populate the tree
        self.list_to_tree(tree_list, self.qtw, self.qtw.columnCount())
        self.qtw.expandAll()

    def list_to_tree(self, tree_list, item, ncols):
        for x in tree_list:
            t = qt.QTreeWidgetItem(item)
            t.setFlags(t.flags() | PyQt5.QtCore.Qt.ItemIsEditable)
            for i in range(ncols):
                if x[i] is not None:
                    t.setText(i, str(x[i]))
                else:
                    t.setText(i, "")

            # if there are children
            self.list_to_tree(x[ncols], t, ncols)

    def save_to_file(self):
        # convert to list
        tree_list = self.tree_to_list(
            self.qtw.invisibleRootItem(), self.qtw.columnCount()
        )

        # write to file
        fname: str = self.parent.config["files"]["sequence_fname"]
        with open(fname, "w") as f:
            json.dump(tree_list, f)

    def tree_to_list(self, item, ncols):
        tree_list = []
        for i in range(item.childCount()):
            row = [item.child(i).text(j) for j in range(ncols)]
            row.append(self.tree_to_list(item.child(i), ncols))
            tree_list.append(row)
        return tree_list

    def add_line(self):
        line = qt.QTreeWidgetItem(self.qtw)
        line.setFlags(line.flags() | PyQt5.QtCore.Qt.ItemIsEditable)

    def remove_line(self):
        for line in self.qtw.selectedItems():
            index = self.qtw.indexOfTopLevelItem(line)
            if index == -1:
                line.parent().takeChild(line.parent().indexOfChild(line))
            else:
                self.qtw.takeTopLevelItem(index)

    def update_progress(self, i):
        self.progress.setValue(i)

    def update_progress_time(self, text: str):
        self.progress.setFormat(text)

    def start_sequencer(self):
        # determine how many times to repeat the entire sequence
        try:
            if "# of repeats" not in self.repeat_le.text():
                n_repeats = int(self.repeat_le.text())
            else:
                n_repeats = 1
        except ValueError as e:
            logging.warning(e)
            n_repeats = 1

        # instantiate and start the thread
        self.sequencer = Sequencer(self.parent, self.circular, n_repeats)
        self.sequencer.start()

        # NB: Qt is not thread safe. Calling SequencerGUI.update_progress()
        # directly from another thread (e.g. from Sequencer) will cause random
        # race-condition segfaults. Instead, the other thread has to emit a
        # Signal, which we here connect to update_progress().
        self.sequencer.progress.connect(self.update_progress)
        self.sequencer.progress_time.connect(self.update_progress_time)
        self.sequencer.finished.connect(self.stop_sequencer)

        # change the "Start" button into a "Stop" button
        self.start_pb.setText("Stop")
        self.start_pb.disconnect()
        self.start_pb.clicked[bool].connect(self.stop_sequencer)

        # show the progress bar
        self.progress.setValue(0)
        self.progress.show()

    def stop_sequencer(self):
        # signal the thread to stop
        if self.sequencer:
            if self.sequencer.active.is_set():
                self.sequencer.active.clear()

        # change the "Stop" button into a "Start" button
        self.start_pb.setText("Start")
        self.start_pb.disconnect()
        self.start_pb.clicked[bool].connect(self.start_sequencer)

        # change the "Resume" button into a "Pause" button; might have paused
        # before stopping sequencer
        self.pause_pb.setText("Pause")
        self.pause_pb.disconnect()
        self.pause_pb.clicked[bool].connect(self.pause_sequencer)

        # hide the progress bar
        self.progress.hide()

    def pause_sequencer(self):
        if self.sequencer:
            self.sequencer.paused.set()
            self.pause_pb.setText("Resume")
            self.pause_pb.disconnect()
            self.pause_pb.clicked[bool].connect(self.resume_sequencer)

    def resume_sequencer(self):
        self.sequencer.paused.clear()
        self.pause_pb.setText("Pause")
        self.pause_pb.disconnect()
        self.pause_pb.clicked[bool].connect(self.pause_sequencer)


class Sequencer(threading.Thread, PyQt5.QtCore.QObject):
    # signal to update the progress bar
    progress = PyQt5.QtCore.pyqtSignal(int)
    progress_time = PyQt5.QtCore.pyqtSignal(str)

    # signal emitted when sequence terminates
    finished = PyQt5.QtCore.pyqtSignal()

    def __init__(self, parent: CentrexGUIProtocol, circular, n_repeats):
        threading.Thread.__init__(self)
        PyQt5.QtCore.QObject.__init__(self)

        # access to the outside world
        self.seqGUI = parent.ControlGUI.seq
        self.devices = parent.devices

        # to enable stopping the thread
        self.active = threading.Event()
        self.active.set()

        # to enable pausing the thread
        self.paused = threading.Event()

        # defaults
        # TODO: use a Config class to do this
        self.default_dt = 1e-4
        self.circular = circular
        self.n_repeats = n_repeats

    def flatten_tree(self, item, parent_info):
        # extract basic information
        dev, fn, wait = item.text(0), item.text(1), item.text(4)

        # extract the parameters
        eval_matches = [
            "linspace",
            "range",
            "arange",
            "logspace",
            "parent_info",
            "array",
        ]
        if any(x in item.text(2) for x in eval_matches):
            try:
                params = eval(item.text(2))
            except Exception as e:
                logging.warning(f"Cannot eval {item.text(2)}: {str(e)}")
                return
        elif "args" in item.text(2):
            try:
                params = [eval(item.text(2).split(":")[-1])]
            except SyntaxError:
                params = [item.text(2).split(":")[-1].split(",")]
        else:
            params = item.text(2).split(",")

        # extract the time delay
        try:
            dt = float(item.text(3))
        except ValueError:
            logging.info(f"Cannot convert to float: {item.text(3)}")
            dt = self.default_dt

        # extract number of repetitions of the line
        try:
            if item.text(5) != "":
                n_rep = int(item.text(5))
            else:
                n_rep = 1
        except ValueError:
            logging.info(f"Cannot convert to int: {item.text(5)}")
            n_rep = 1

        # iterate over the given parameter list
        for i in range(n_rep):
            for p in params:
                if isinstance(p, str):
                    p = parse_dummy_variables(p, parent_info)
                elif isinstance(p, (list, tuple)):
                    p = [
                        parse_dummy_variables(pi, parent_info)
                        if isinstance(pi, str)
                        else pi
                        for pi in p
                    ]

                if dev and fn:
                    if dev in self.devices:
                        self.flat_seq.append([dev, fn, p, dt, wait, parent_info])
                    else:
                        logging.warning(f"Device does not exist: {dev}")
                else:
                    self.flat_seq.append((None, None, p, dt, wait, parent_info))

                # get information about the item's children
                child_count = item.childCount()
                for i in range(child_count):
                    self.flatten_tree(item.child(i), parent_info + [[dev, fn, p]])

    def run(self):
        # flatten the tree into sequence of rows
        self.flat_seq = []
        root = self.seqGUI.qtw.invisibleRootItem()
        self.flatten_tree(root, parent_info=[])
        self.seqGUI.progress.setMaximum(len(self.flat_seq))

        # repeat the entire sequence n times
        self.flat_seq = self.n_repeats * self.flat_seq

        # if we want to cycle over the same loop forever
        if self.circular:
            self.flat_seq = itertools.cycle(self.flat_seq)

        start_time = time.time()
        total_commands = len(self.flat_seq)

        # main sequencer loop
        for i, (dev, fn, p, dt, wait, parent_info) in enumerate(self.flat_seq):
            # check for user stop request
            while self.paused.is_set():
                if (dev == "PXIe5171") & (fn == "ReadValue"):
                    break
                time.sleep(1e-3)
            if not self.active.is_set():
                return

            # enqueue the commands and wait
            id0 = time.time_ns()
            if dev is not None:
                self.devices[dev].sequencer_commands.append([id0, f"{fn}({p})"])
                time.sleep(dt)

                # wait till completion, if requested
                if wait:
                    finished = False
                    while not finished:
                        # check for user stop request
                        if not self.active.is_set():
                            return

                        # look for return values
                        try:
                            id1, _, _, _ = self.devices[
                                dev
                            ].sequencer_events_queue.pop()
                            if id1 == id0:
                                finished = True
                        except IndexError:
                            time.sleep(self.default_dt)

            # progress bar
            time_elapsed = time.time() - start_time
            time_estimate = total_commands * (time_elapsed) / (i + 1)
            time_remaining = round(time_estimate - time_elapsed, 0)
            timedelta_remaining = datetime.timedelta(seconds=time_remaining)
            # update progress bar
            self.progress.emit(i)
            self.progress_time.emit(f"%p%, {timedelta_remaining} remaining")

        # when finished
        self.progress.emit(len(self.flat_seq))
        self.finished.emit()
