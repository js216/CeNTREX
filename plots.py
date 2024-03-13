import logging
import pickle
import time
import traceback

import numpy as np
import numpy.typing as npt
import pyqtgraph as pg
import PySide6
import PySide6.QtWidgets as qt

from config import PlotConfig
from device import Device
from protocols import CentrexGUIProtocol
from utils_gui import LabelFrame, ScrollableLabelFrame, update_QComboBox


class PlotsGUI(qt.QSplitter):
    def __init__(self, parent: CentrexGUIProtocol):
        super().__init__()
        self.parent: CentrexGUIProtocol = parent
        self.all_plots = {}
        self.place_GUI_elements()

        # QSplitter options
        self.setSizes([1, 10000])
        self.setOrientation(PySide6.QtCore.Qt.Vertical)

    def place_GUI_elements(self):
        # controls for all plots
        self.ctrls_box, ctrls_f = LabelFrame("Controls")
        self.addWidget(self.ctrls_box)
        ctrls_f.setColumnStretch(1, 1)

        pb = qt.QPushButton("Start all")
        pb.setToolTip("Start all plots (Ctrl+Shift+S).")
        pb.clicked[bool].connect(self.start_all_plots)
        ctrls_f.addWidget(pb, 0, 0)

        pb = qt.QPushButton("Stop all")
        pb.setToolTip("Stop all plots (Ctrl+Shift+Q).")
        pb.clicked[bool].connect(self.stop_all_plots)
        ctrls_f.addWidget(pb, 0, 1)

        pb = qt.QPushButton("Delete all")
        pb.clicked[bool].connect(self.destroy_all_plots)
        ctrls_f.addWidget(pb, 0, 2)

        # for setting refresh rate of all plots
        self.dt_qle = qt.QLineEdit()
        self.dt_qle.setText("plot refresh rate")
        self.dt_qle.setToolTip(
            "Delay between updating all plots, i.e. smaller dt means faster plot"
            " refresh rate."
        )
        self.dt_qle.textChanged[str].connect(self.set_all_dt)
        ctrls_f.addWidget(self.dt_qle, 0, 3)

        # for setting x limits of all plots

        qle = qt.QLineEdit()
        qle.setText("x0")
        qle.setToolTip("Set the index of first point to plot for all plots.")
        qle.textChanged[str].connect(self.set_all_x0)
        ctrls_f.addWidget(qle, 1, 3)

        qle = qt.QLineEdit()
        qle.setText("x1")
        qle.setToolTip("Set the index of last point to plot for all plots.")
        qle.textChanged[str].connect(self.set_all_x1)
        ctrls_f.addWidget(qle, 1, 4)

        # button to add plot in the specified column
        qle = qt.QLineEdit()
        qle.setText("col for new plots")
        qle.setToolTip("Column to place new plots in.")
        ctrls_f.addWidget(qle, 0, 4)
        pb = qt.QPushButton("New plot ...")
        pb.setToolTip("Add a new plot in the specified column.")
        ctrls_f.addWidget(pb, 0, 5)
        pb.clicked[bool].connect(lambda val, qle=qle: self.add_plot(col=qle.text()))

        # button to toggle plot controls visible/invisible
        pb = qt.QPushButton("Toggle controls")
        pb.setToolTip("Show or hide individual plot controls (Ctrl+T).")
        ctrls_f.addWidget(pb, 1, 5)
        pb.clicked[bool].connect(lambda val: self.toggle_all_plot_controls())

        # for saving plot configuration
        ctrls_f.addWidget(qt.QLabel("Plot config file:"), 2, 0)

        qle = qt.QLineEdit()
        qle.setText(str(self.parent.config.files.plotting_config_fname))
        qle.textChanged[str].connect(
            lambda val: self.parent.config.change("files", "plotting_config_fname", val)
        )
        ctrls_f.addWidget(qle, 2, 1)

        pb = qt.QPushButton("Open....")
        ctrls_f.addWidget(pb, 2, 2)
        pb.clicked[bool].connect(
            lambda val, qle=qle: self.open_file("files", "plotting_config_fname", qle)
        )

        pb = qt.QPushButton("Save plots")
        ctrls_f.addWidget(pb, 2, 3)
        pb.clicked[bool].connect(lambda val, fname=qle.text(): self.save_plots(fname))

        pb = qt.QPushButton("Load plots")
        ctrls_f.addWidget(pb, 2, 4)
        pb.clicked[bool].connect(lambda val, fname=qle.text(): self.load_plots(fname))

        # frame to place all the plots in
        box, self.plots_f = LabelFrame("Plots")
        self.addWidget(box)

        # add one plot
        self.add_plot()

    def add_plot(self, row=None, col=None):
        # find column for the plot if not given to the function
        try:
            if col == "col for new plots":
                col = 0
            else:
                col = int(col) if col else 0
        except (ValueError, TypeError):
            logging.info(traceback.format_exc())
            col = 0

        # find row for the plot if not given to the function
        try:
            if row:
                row = int(row)
            else:
                row = 0
                for row_key, plot in self.all_plots.setdefault(col, {0: None}).items():
                    if plot:
                        row += 1
        except ValueError:
            logging.error("Row name not valid.")
            logging.error(traceback.format_exc())
            return

        # frame for the plot
        box = qt.QSplitter()
        box.setOrientation(PySide6.QtCore.Qt.Vertical)
        self.plots_f.addWidget(box, row, col)

        # place the plot
        plot = Plotter(box, self.parent)
        plot.config.row, plot.config.col = row, col
        self.all_plots.setdefault(
            col, {0: None}
        )  # check the column is in the dict, else add it
        self.all_plots[col][row] = plot

        return plot

    def open_file(self, sect, config, qle):
        val = qt.QFileDialog.getOpenFileName(self, "Select file")[0]
        if not val:
            return
        self.parent.config.change(sect, config, val)
        qle.setText(val)

    def start_all_plots(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.start_animation()

    def stop_all_plots(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.stop_animation()

    def destroy_all_plots(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.destroy()

    def set_all_x0(self, x0):
        # sanity check
        try:
            x0 = int(x0)
        except ValueError:
            logging.info(traceback.format_exc())
            x0 = 0

        # set the value
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.config.change("x0", x0)
                    plot.x0_qle.setText(str(x0))

    def set_all_x1(self, x1):
        # sanity check
        try:
            x1 = int(x1)
        except ValueError:
            logging.info(traceback.format_exc())
            x1 = -1

        # set the value
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.config.change("x1", x1)
                    plot.x1_qle.setText(str(x1))

    def set_all_dt(self, dt):
        # sanity check
        try:
            dt = float(dt)
            if dt < 0.002:
                logging.warning("Plot dt too small.")
                raise ValueError
        except ValueError:
            logging.info(traceback.format_exc())
            dt = float(self.parent.config.general.plot_dt)

        # set the value
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.config.change("dt", dt)
                    plot.dt_qle.setText(str(dt))

    def clear_all_fast_y(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.fast_y = []

    def toggle_all_plot_controls(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.toggle_controls()

    def save_plots(self, dt):
        # put essential information about plot configuration in a dictionary
        plot_configs = {}
        for col, col_plots in self.all_plots.items():
            plot_configs[col] = {}
            for row, plot in col_plots.items():
                if plot:
                    plot_configs[col][row] = plot.config.get_static_params()

        # save this info as a pickled dictionary
        with open(self.parent.config.files.plotting_config_fname, "wb") as f:
            pickle.dump(plot_configs, f)

    def load_plots(self, dt):
        # remove all plots
        self.destroy_all_plots()

        # read pickled plot config
        try:
            with open(self.parent.config.files.plotting_config_fname, "rb") as f:
                plot_configs = pickle.load(f)
        except OSError as err:
            logging.warning("Warning in load_plots: " + str(err))
            logging.warning(traceback.format_exc())
            return

        # re-create all plots
        for col, col_plots in plot_configs.items():
            for row, config in col_plots.items():
                # add a plot
                plot = self.add_plot(row, col)

                # restore configuration
                plot.config = PlotConfig(config)

                # set the GUI elements to the restored values
                plot.x0_qle.setText(config.x0)
                plot.x1_qle.setText(config.x1)
                plot.y0_qle.setText(config.y0)
                plot.y1_qle.setText(config.y1)
                plot.dt_qle.setText(str(config.dt))
                plot.fn_qle.setText(config.fy)
                plot.avg_qle.setText(str(config.n_average))
                plot.refresh_parameter_lists(select_defaults=False)


def get_data_slow_queue(
    device: Device, param_list: list[str], config: PlotConfig
) -> tuple[npt.NDArray[np.float_ | np.int_ | np.bool_]] | None:
    if len(device.config.plots_queue) < 2:
        return None

    x = np.array([getattr(d, config.x) for d in device.config.plots_queue])
    y = np.array([getattr(d, config.y) for d in device.config.plots_queue])

    # divide y by z (if applicable)
    if config.z in param_list and config.z != "(none)":
        z = np.array([getattr(d, config.y) for d in device.config.plots_queue])
        y = y / z

    return x, y


def get_data_fast_queue(
    device: Device, param_list: list[str], config: PlotConfig
) -> (
    tuple[
        npt.NDArray[np.int_ | np.float_ | np.bool_],
        npt.NDArray[np.int_ | np.float_ | np.bool_],
    ]
    | None
):
    try:
        data = device.config.plots_queue[-1]
    except IndexError as e:
        logging.warning(e)
        logging.warning(traceback.format_exc())
        return None
    if config.x == "(none)":
        x = np.arange(data.data.shape[2])
    else:
        x = data.data[0, param_list.index(config.x)].astype(float)
    if config.y == "(none)":
        logging.warning("Plot error: y not valid.")
        logging.warning("Plot warning: bad parameters")
        return None
    y = data.data[0, param_list.index(config.y)].astype(float)

    # divide y by z (if applicable)
    if config.z in param_list and config.z != "(none)":
        y = y / data.data[0, param_list.index(config.z)]

    # if not averaging, return the data
    if config.n_average < 2:
        return x, y

    # average sanity check
    if config.n_average > device.config.plots_queue_maxlen:
        logging.warning(
            "Plot error: Cannot average more traces than are stored in"
            " plots_queue when plotting from the queue."
        )
        return x, y

    # averaging

    plots_queue = np.array([dset.data for dset in device.config.plots_queue])

    idy = param_list.index(config.y)
    y = plots_queue[:, idy, :]

    if config.z in param_list and config.z != "(none)":
        idz = param_list.index(config.z)
        z = plots_queue[:, idz, :]
        y = y / z

    return x, y[-config.n_average :].mean(axis=0)


class Plotter(qt.QWidget):
    def __init__(self, frame, parent: CentrexGUIProtocol):
        super().__init__()
        self.f = frame
        self.parent: CentrexGUIProtocol = parent

        self.plot = None
        self.curve = None
        self.fast_y = []

        self.config = PlotConfig()

        self.place_GUI_elements()

    def toggle_controls(self):
        if self.config.controls:
            self.config.controls = False
            self.ctrls_box.hide()
        else:
            self.config.controls = True
            self.ctrls_box.show()

    def place_GUI_elements(self):
        # scrollable area for controls
        self.ctrls_box, ctrls_f = ScrollableLabelFrame(
            "", fixed=True, vert_scroll=False
        )
        self.f.addWidget(self.ctrls_box)

        # select device
        self.dev_cbx = qt.QComboBox()
        self.dev_cbx.activated[int].connect(
            lambda val: self.config.change("device", self.dev_cbx.itemText(val))
        )
        self.dev_cbx.activated[int].connect(
            lambda val: self.refresh_parameter_lists(select_plots_fn=True)
        )
        self.dev_cbx.activated[int].connect(self.update_labels)
        update_QComboBox(
            cbx=self.dev_cbx,
            options=self.parent.ControlGUI.get_dev_list(),
            value=self.config.device,
        )
        ctrls_f.addWidget(self.dev_cbx, 0, 0)

        # select x, y, and z

        self.x_cbx = qt.QComboBox()
        self.x_cbx.setToolTip("Select the independent variable.")
        self.x_cbx.activated[int].connect(
            lambda val: self.config.change("x", self.x_cbx.itemText(val))
        )
        self.x_cbx.activated[int].connect(self.update_labels)
        ctrls_f.addWidget(self.x_cbx, 1, 0)

        self.y_cbx = qt.QComboBox()
        self.y_cbx.setToolTip("Select the dependent variable.")
        self.y_cbx.activated[int].connect(
            lambda val: self.config.change("y", self.y_cbx.itemText(val))
        )
        self.y_cbx.activated[int].connect(self.update_labels)
        ctrls_f.addWidget(self.y_cbx, 1, 1)

        self.z_cbx = qt.QComboBox()
        self.z_cbx.setToolTip("Select the variable to divide y by.")
        self.z_cbx.activated[int].connect(
            lambda val: self.config.change("z", self.z_cbx.itemText(val))
        )
        self.z_cbx.activated[int].connect(self.update_labels)
        ctrls_f.addWidget(self.z_cbx, 1, 2)

        # plot range controls
        self.x0_qle = qt.QLineEdit()
        self.x0_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.x0_qle, 1, 3)
        self.x0_qle.setText(self.config.x0)
        self.x0_qle.setToolTip("x0 = index of first point to plot")
        self.x0_qle.textChanged[str].connect(lambda val: self.config.change("x0", val))

        self.x1_qle = qt.QLineEdit()
        self.x1_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.x1_qle, 1, 4)
        self.x1_qle.setText(self.config.x1)
        self.x1_qle.setToolTip("x1 = index of last point to plot")
        self.x1_qle.textChanged[str].connect(lambda val: self.config.change("x1", val))

        self.y0_qle = qt.QLineEdit()
        self.y0_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.y0_qle, 1, 5)
        self.y0_qle.setText(self.config.y0)
        self.y0_qle.setToolTip("y0 = lower y limit")
        self.y0_qle.textChanged[str].connect(lambda val: self.config.change("y0", val))
        self.y0_qle.textChanged[str].connect(lambda val: self.change_y_limits())

        self.y1_qle = qt.QLineEdit()
        self.y1_qle.setMaximumWidth(50)
        ctrls_f.addWidget(self.y1_qle, 1, 6)
        self.y1_qle.setText(self.config.y1)
        self.y1_qle.setToolTip("y1 = upper y limit")
        self.y1_qle.textChanged[str].connect(lambda val: self.config.change("y1", val))
        self.y1_qle.textChanged[str].connect(lambda val: self.change_y_limits())

        # plot refresh rate
        self.dt_qle = qt.QLineEdit()
        self.dt_qle.setMaximumWidth(50)
        self.dt_qle.setText("dt")
        self.dt_qle.setToolTip(
            "Delay between updating the plot, i.e. smaller dt means faster plot refresh"
            " rate."
        )
        self.dt_qle.textChanged[str].connect(lambda val: self.config.change("dt", val))
        ctrls_f.addWidget(self.dt_qle, 1, 7)

        # start button
        self.start_pb = qt.QPushButton("Start")
        self.start_pb.setMaximumWidth(50)
        self.start_pb.clicked[bool].connect(self.start_animation)
        ctrls_f.addWidget(self.start_pb, 0, 3)

        # toggle log/lin
        pb = qt.QPushButton("Log/Lin")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_log_lin)
        ctrls_f.addWidget(pb, 0, 4)

        # toggle lines/points
        pb = qt.QPushButton("\u26ab / \u2014")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_points)
        ctrls_f.addWidget(pb, 0, 5)

        # toggle histogram
        pb = qt.QPushButton("hist")
        pb.setMaximumWidth(50)
        pb.clicked[bool].connect(self.toggle_hist)
        ctrls_f.addWidget(pb, 0, 7)

        # for displaying a function of the data

        self.fn_qle = qt.QLineEdit()
        self.fn_qle.setText(self.config.fy)
        self.fn_qle.setToolTip("Apply the specified function before plotting the data.")
        self.fn_qle.textChanged[str].connect(lambda val: self.config.change("fy", val))
        ctrls_f.addWidget(self.fn_qle, 0, 2)

        self.fn_pb = qt.QPushButton("f(y)")
        self.fn_pb.setToolTip(
            "Apply the specified function before plotting the data. Double click to"
            " clear the old calculations for fast data."
        )
        self.fn_pb.setMaximumWidth(50)
        self.fn_pb.clicked[bool].connect(self.toggle_fn)
        ctrls_f.addWidget(self.fn_pb, 0, 6)

        # for averaging last n curves
        self.avg_qle = qt.QLineEdit()
        self.avg_qle.setMaximumWidth(50)
        self.avg_qle.setToolTip(
            "Enter the number of traces to average. Default = 1, i.e. no averaging."
        )
        self.avg_qle.setText("avg?")
        self.avg_qle.textChanged[str].connect(
            lambda val: self.config.change("n_average", val)
        )
        ctrls_f.addWidget(self.avg_qle, 1, 8)

        # button to delete plot
        pb = qt.QPushButton("\u274c")
        pb.setMaximumWidth(50)
        pb.setToolTip("Delete the plot")
        ctrls_f.addWidget(pb, 0, 9)
        pb.clicked[bool].connect(lambda val: self.destroy())

        # update the values of the above controls
        self.refresh_parameter_lists(select_plots_fn=True)

    def refresh_parameter_lists(self, select_defaults=True, select_plots_fn=False):
        # update the list of available devices
        available_devices = self.parent.ControlGUI.get_dev_list()
        update_QComboBox(
            cbx=self.dev_cbx, options=available_devices, value=self.config.device
        )

        # check device is available, else select the first device on the list
        if self.config.device in available_devices:
            self.dev = self.parent.devices[self.config.device]
        elif len(self.parent.devices) != 0:
            self.config.device = available_devices[0]
            self.dev = self.parent.devices[self.config.device]
        else:
            logging.warning("Plot error: No devices in self.parent.devices.")
            return
        self.dev_cbx.setCurrentText(self.config.device)

        # get parameters
        # self.param_list = split(self.dev.config["attributes"]["column_names"])
        if self.dev.config.slow_data:
            self.param_list = self.dev.config.attributes.column_names
        elif not self.dev.config.slow_data:
            self.param_list = self.dev.config.attributes.column_names + ["(none)"]
        if not self.param_list:
            logging.warning("Plot error: No parameters to plot.")
            return

        # check x and y are good
        if self.config.x not in self.param_list:
            if self.dev.config.slow_data:  # fast data does not need an x variable
                select_defaults = True
        if self.config.y not in self.param_list:
            select_defaults = True

        # select x and y
        if select_defaults:
            if self.dev.config.slow_data:
                self.config.x = self.param_list[0]
                self.config.y = self.param_list[1]
            else:
                self.config.x = "(none)"
                self.config.y = self.param_list[0]

        # update the default plot f(y) for the given device
        if select_plots_fn:
            self.config.fy = self.dev.config.plots_fn
            self.fn_qle.setText(self.config.fy)

        # update x, y, and z QComboBoxes
        update_QComboBox(cbx=self.x_cbx, options=self.param_list, value=self.config.x)
        update_QComboBox(cbx=self.y_cbx, options=self.param_list, value=self.config.y)
        update_QComboBox(
            cbx=self.z_cbx,
            options=["divide by?"] + self.param_list,
            value=self.config.z,
        )

    def clear_fn(self):
        """Clear the arrays of past evaluations of the custom function on the data."""
        self.x, self.y = [], []

    def parameters_good(self) -> bool:
        # check device is valid
        if self.config.device in self.parent.devices:
            self.dev = self.parent.devices[self.config.device]
        else:
            self.stop_animation()
            logging.warning("Plot error: Invalid device: " + self.config.device)
            return False

        # check parameters are valid, fast data does not need an x variable
        if self.config.x not in self.param_list and self.dev.config.slow_data:
            logging.warning("Plot warning: x not valid.")
            return False

        if self.config.y not in self.param_list:
            logging.warning("Plot error: y not valid.")
            return False

        # return
        return True

    def get_raw_data_from_queue(self):
        if self.dev.config.slow_data:
            return get_data_slow_queue(self.dev, self.param_list, self.config)
        else:
            return get_data_fast_queue(self.dev, self.param_list, self.config)

    def get_data(self):
        data = self.get_raw_data_from_queue()

        try:
            x, y = data[0], data[1]
            if len(x) < 2:  # require at least two datapoints
                raise ValueError("Require at least two datapoints")
        except (ValueError, TypeError) as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            return None

        # select indices for subsetting
        try:
            _x0: str = self.config.x0
            _x1: str = self.config.x1
            if _x0 == "x0" or _x1 == "x1":
                x0, x1 = 0, len(x)
            else:
                x0 = int(float(_x0))
                x1 = int(float(_x1))
        except ValueError as e:
            logging.warning(e)
            logging.warning(traceback.format_exc())
            x0, x1 = 0, len(x)
        if x0 >= x1:
            if x1 >= 0:
                x0, x1 = 0, len(x)
        if x1 >= len(x) - 1:
            x0, x1 = 0, len(x)

        # verify data shape
        if not x.shape == y.shape:
            logging.warning(
                f"Plot error: data shapes not mathching: {x.shape} != {y.shape}"
            )
            return None

        # if not applying f(y), return the data ...
        if not self.config.fn:
            return x[x0:x1], y[x0:x1]

        # ... else apply f(y) to the data

        if self.dev.config.slow_data:
            # For slow data, the function evaluated on the data must return an
            # array of the same shape as the raw data.
            try:
                y_fn = eval(self.config.fy)
                if not x.shape == y_fn.shape:
                    raise ValueError("x.shape != y_fn.shape")
            except Exception as err:
                logging.warning(str(err))
                logging.warning(traceback.format_exc())
                y_fn = y
            else:
                return x[x0:x1], y_fn[x0:x1]

        if not self.dev.config.slow_data:
            # For fast data, the function evaluated on the data must return either
            #    (a) an array with same shape as the original data
            #    (b) a scalar value
            try:
                y_fn = eval(self.config.fy)
                # case (a)
                if x.shape == y_fn.shape:
                    return x[x0:x1], y_fn[x0:x1]

                # case (b)
                else:
                    try:
                        float(y_fn)
                        self.fast_y.append(y_fn)
                        return np.arange(len(self.fast_y)), np.array(self.fast_y)
                    except Exception as err:
                        raise TypeError(str(err))

            except Exception as e:
                logging.warning(e)
                logging.warning(traceback.format_exc())
                return x[x0:x1], y[x0:x1]

    def replot(self) -> None:
        # check parameters
        if not self.parameters_good():
            logging.warning("Plot warning: bad parameters.")
            return

        # get data
        data = self.get_data()
        if not data:
            return

        # plot data
        if not self.plot:
            self.plot = pg.PlotWidget()
            self.plot.showGrid(True, True)
            self.f.addWidget(self.plot)
        if not self.curve:
            if self.config.hist:
                dx = data[0][1] - data[0][0]
                x = np.append(data[0] - dx / 2, data[0][-1] + dx / 2)
                data = (x, data[1])
            self.curve = self.plot.plot(
                *data,
                symbol=self.config.symbol,
                stepMode="center" if self.config.hist else None,
            )
            self.update_labels()
        else:
            if self.config.hist:
                dx = data[0][1] - data[0][0]
                x = np.append(data[0] - dx / 2, data[0][-1] + dx / 2)
                data = (x, data[1])
            self.curve.setData(*data)

    def update_labels(self) -> None:
        if self.plot:
            # get units
            col_names = self.dev.config.attributes.column_names
            units = self.dev.config.attributes.units
            try:
                if self.config.x == "(none)":
                    x_unit = ""
                else:
                    x_unit = " [" + units[col_names.index(self.config.x)] + "]"
                if self.config.y == "(none)":
                    y_unit = ""
                else:
                    y_unit = " [" + units[col_names.index(self.config.y)] + "]"
            except ValueError as e:
                logging.warning(e)
                logging.warning(traceback.format_exc())
                x_unit, y_unit = "", ""

            # set axis labels
            self.plot.setLabel("bottom", self.config.x + x_unit)
            self.plot.setLabel("left", self.config.y + y_unit)

            # set plot title
            title = self.config.device
            if self.config.fn:
                title += "; applying function:" + str(self.config.fy)
            if self.config.z in col_names:
                title += "; dividing by " + str(self.config.z)
            self.plot.setLabel("top", title)

    def change_y_limits(self) -> None:
        if self.plot:
            try:
                y0 = float(self.config.y0)
                y1 = float(self.config.y1)
            except ValueError as e:
                logging.warning(e)
                logging.warning(traceback.format_exc())
                self.plot.enableAutoRange()
            else:
                self.plot.setYRange(y0, y1)

    class PlotUpdater(PySide6.QtCore.QThread):
        signal = PySide6.QtCore.Signal()

        def __init__(self, parent: CentrexGUIProtocol, config: PlotConfig):
            self.parent: CentrexGUIProtocol = parent
            self.config = config
            super().__init__()

        def run(self):
            while self.config.active:
                self.signal.emit()

                # loop delay
                try:
                    dt = float(self.config.dt)
                    if dt < 0.002:
                        logging.warning("Plot dt too small.")
                        raise ValueError(f"{dt} < 0.002")
                except ValueError as e:
                    logging.warning(e)
                    logging.warning(traceback.format_exc())
                    dt = float(self.parent.config.general.plot_dt)
                time.sleep(dt)
            logging.info(f"PlotUpdater: {self.config.device} stopped")

    def start_animation(self):
        # start animation
        self.thread = self.PlotUpdater(self.parent, self.config)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        self.thread.signal.connect(self.replot)

        # update status
        self.config.active = True

        # change the "Start" button into a "Stop" button
        self.start_pb.setText("Stop")
        # self.start_pb.disconnect()
        self.start_pb.clicked[bool].connect(self.stop_animation)

    def stop_animation(self):
        if not self.config.active:
            return

        # stop animation
        self.config.active = False

        # change the "Stop" button into a "Start" button
        self.start_pb.setText("Start")
        # self.start_pb.disconnect()
        self.start_pb.clicked[bool].connect(self.start_animation)
        self.thread.exit()
        self.thread.wait()

    def destroy(self):
        self.stop_animation()
        # get the position of the plot
        row, col = self.config.row, self.config.col

        # remove the plot from the all_plots dict
        self.parent.PlotsGUI.all_plots[col][row] = None

        # remove the GUI elements related to the plot
        try:
            self.parent.PlotsGUI.plots_f.itemAtPosition(row, col).widget().setParent(
                None
            )
        except AttributeError as err:
            logging.warning("Plot warning: cannot remove plot: " + str(err))
            logging.warning(traceback.format_exc())

    def toggle_log_lin(self):
        if not self.config.log:
            self.config.log = True
            self.plot.setLogMode(False, True)
        else:
            self.config.log = False
            self.plot.setLogMode(False, False)

    def toggle_points(self):
        if not self.config.symbol:
            if self.curve is not None:
                self.curve.clear()
                self.curve = None
            self.curve = None
            self.config.symbol = "o"
        else:
            if self.curve is not None:
                self.curve.clear()
                self.curve = None
            self.curve = None
            self.config.symbol = None

    def toggle_fn(self):
        if not self.config.fn:
            self.config.fn = True
            self.fn_pb.setText("Raw")
            self.fn_pb.setToolTip(
                "Display raw data and/or clear the old calculations for fast data."
            )
        else:
            self.config.fn = False
            self.fast_y = []
            self.fn_pb.setText("f(y)")
            self.fn_pb.setToolTip(
                "Apply the specified function before plotting the data. Double click to"
                " clear the old calculations for fast data."
            )

        # display the function in the plot title (or not)
        self.update_labels()

    def toggle_hist(self):
        if not self.config.hist:
            if self.curve is not None:
                self.curve.clear()
                self.curve = None
            self.curve = None
            self.config.hist = True
        else:
            if self.curve is not None:
                self.curve.clear()
                self.curve = None
            self.curve = None
            self.config.hist = None
