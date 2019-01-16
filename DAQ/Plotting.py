import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.animation as animation
import numpy as np
import sys, time
import csv
import gc
import h5py
import logging
from scipy import integrate

class PlotsGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        # variable to keep track of the plots
        self.all_plots = {}

        # main frame for all PlotsGUI elements
        self.nb_frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.nb_frame, text="Plots")

        # frame
        self.f = tk.Frame(self.nb_frame)
        self.f.grid(row=0, column=0, sticky='n')

        # controls for all plots
        ctrls_f = tk.LabelFrame(self.f, text="Plot controls")
        ctrls_f.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)
        tk.Button(ctrls_f, text="Start all", command=self.start_all)\
                .grid(row=0, column=0, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Stop all", command=self.stop_all)\
                .grid(row=0, column=1, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Delete all", command=self.delete_all)\
                .grid(row=0, column=3, sticky='e', padx=10)

        # for setting refresh rate of all plots
        self.dt_var = tk.StringVar()
        self.dt_var.set("dt")
        dt_entry = tk.Entry(ctrls_f, textvariable=self.dt_var, width=7)
        dt_entry.grid(row=0, column=4, sticky='w', padx=5)
        dt_entry.bind("<Return>", self.change_all_animation_dt)

        # control to select how many data points to display in a graph (to speed up plotting)
        self.max_pts = tk.StringVar()
        self.max_pts.set("max_pts")
        tk.Entry(ctrls_f, textvariable=self.max_pts, width=13).grid(row=0, column=6, sticky='w', padx=5)

        # button to add add plot in the specified column
        self.col_var = tk.StringVar()
        self.col_var.set("plot column")
        tk.Entry(ctrls_f, textvariable=self.col_var, width=13).grid(row=0, column=7, sticky='w', padx=5)
        tk.Button(ctrls_f, text="New plot ...", command=self.add_plot)\
            .grid(row=0, column=8, sticky='e', padx=10)

        # the HDF file we're currently plotting from
        tk.Label(ctrls_f, text="HDF file:")\
                .grid(row=1, column=0)
        tk.Entry(ctrls_f,
                textvariable=self.parent.config["files"]["plotting_hdf_fname"])\
                .grid(row=1, column=1, columnspan=5, padx=10, sticky="ew")
        tk.Button(ctrls_f, text="Open...",
                command = lambda: self.open_HDF_file("plotting_hdf_fname"))\
                .grid(row=1, column=6, padx=10, sticky='ew')

        # add one plot
        self.add_plot()

    def open_HDF_file(self, prop):
        # ask for a file name
        fname = filedialog.askopenfilename(
                initialdir = self.parent.config["files"][prop].get(),
                title = "Select file",
                filetypes = (("HDF files","*.h5"),("all files","*.*")))

        # check a filename was returned
        if not fname:
            return

        # check it's a valid HDF file
        try:
            with h5py.File(fname, 'r') as f:
                self.parent.config["files"][prop].set(fname)
                self.refresh_run_list(fname)
        except OSError:
            messagebox.showerror("File error", "Not a valid HDF file.")

    def change_all_animation_dt(self, i=0):
        # determine what the plot refresh rate is
        try:
            dt = float(self.dt_var.get())
        except ValueError:
            dt = 1
        if dt < 0.01:
            dt = 0.01

        # set all plots to that refresh rate
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.change_animation_dt(0, dt)

    def refresh_run_list(self, fname):
        # get list of runs
        with h5py.File(fname, 'r') as f:
            self.run_list = list(f.keys())

        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    # update the OptionMenu
                    menu = plot.run_select["menu"]
                    menu.delete(0, "end")
                    for p in self.run_list:
                        menu.add_command(label=p, command=lambda val=p: plot.run_var.set(val))

                    # select the last run by default
                    plot.run_var.set(self.run_list[-1])

    def delete_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.destroy()
        self.all_plots = {}

    def start_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.start_animation()

    def stop_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.stop_animation()

    def refresh_all_parameter_lists(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.refresh_parameter_list(plot.dev_var.get())

    def add_plot(self):
        # find location for the plot
        try:
            col = int(self.col_var.get())
        except ValueError:
            col = 0
        row = max([ r for r in self.all_plots.setdefault(col, {0:None}) ]) + 2

        # frame for the plot
        fr = tk.LabelFrame(self.f, text="")
        fr.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        # place the plot
        plot = Plotter(fr, self.parent)
        self.all_plots[col][row] = plot

        # button to delete plot
        del_b = tk.Button(plot.f, text="\u274c", command=lambda plot=plot,
                row=row, col=col: self.delete_plot(row,col,plot))
        del_b.grid(row=0, column=8, sticky='e', padx=10)

        # update list of runs if a file was supplied
        fname = self.parent.config["files"]["plotting_hdf_fname"].get()
        try:
            with h5py.File(fname, 'r') as f:
                self.run_list = list(f.keys())
                menu = plot.run_select["menu"]
                menu.delete(0, "end")
                for p in self.run_list:
                    menu.add_command(label=p, command=lambda val=p: plot.run_var.set(val))
                plot.run_var.set(self.run_list[-1])
        except OSError:
            pass

    def delete_plot(self, row, col, plot):
        if plot:
            plot.destroy()
        self.all_plots[col].pop(row, None)

class Plotter(tk.Frame):
    def __init__(self, frame, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.f = frame
        self.parent = parent
        self.log = False
        self.points = False
        self.plot_drawn = False
        self.record_number = tk.StringVar()
        self.animation_running = False

        # select device
        self.dev_list = [dev_name.strip() for dev_name in self.parent.devices]
        if not self.dev_list:
            self.dev_list = ["(no devices)"]
        self.dev_var = tk.StringVar()
        self.dev_var.set(self.dev_list[0])
        dev_select = tk.OptionMenu(self.f, self.dev_var, *self.dev_list,
                command=self.refresh_parameter_list)
        dev_select.grid(row=0, column=0, columnspan=1, sticky='ew')
        dev_select.configure(width=22)

        # select run
        self.run_list = [""]
        self.run_var = tk.StringVar()
        self.run_var.set("Select run ...")
        self.run_select = tk.OptionMenu(self.f, self.run_var, *self.run_list)
        self.run_select.grid(row=0, column=1, columnspan=1, sticky='ew')
        self.run_select.configure(width=18)

        # select parameter
        self.param_list = ["(select device first)"]
        self.param_var = tk.StringVar()
        self.param_var.set("y ...")
        self.param_select = tk.OptionMenu(self.f, self.param_var, *self.param_list)
        self.param_select.grid(row=1, column=1, columnspan=1, sticky='ew')
        self.param_select.configure(width=18)

        # select xcol
        self.xcol_list = ["(select device first)"]
        self.xcol_var = tk.StringVar()
        self.xcol_var.set("x ...")
        self.xcol_select = tk.OptionMenu(self.f, self.xcol_var, *self.xcol_list)
        self.xcol_select.grid(row=1, column=0, columnspan=1, sticky='ew')
        self.xcol_select.configure(width=18)

        self.refresh_parameter_list(self.dev_var.get())



        # plot range controls
        num_width = 7 # width of numeric entry boxes
        self.x0_var = tk.StringVar()
        self.x0_var.set("x0")
        tk.Entry(self.f, textvariable=self.x0_var, width=num_width)\
                .grid(row=1, column=2, columnspan=2, sticky='w', padx=1)
        self.x1_var = tk.StringVar()
        self.x1_var.set("x1")
        tk.Entry(self.f, textvariable=self.x1_var, width=num_width)\
                .grid(row=1, column=4, sticky='w', padx=1)
        self.y0_var = tk.StringVar()
        self.y0_var.set("y0")
        tk.Entry(self.f, textvariable=self.y0_var, width=num_width)\
                .grid(row=1, column=5, sticky='w', padx=1)
        self.y1_var = tk.StringVar()
        self.y1_var.set("y1")
        tk.Entry(self.f, textvariable=self.y1_var, width=num_width)\
                .grid(row=1, column=6, sticky='w', padx=1)

        # control buttons
        self.dt_var = tk.StringVar()
        self.dt_var.set("dt")
        dt_entry = tk.Entry(self.f, textvariable=self.dt_var, width=num_width)
        dt_entry.grid(row=1, column=7, columnspan=1)
        dt_entry.bind("<Return>", self.change_animation_dt)
        self.play_pause_button = tk.Button(self.f, text="\u25b6", command=self.start_animation)
        self.play_pause_button.grid(row=0, column=5, padx=2)
        tk.Button(self.f, text="Log/Lin", command=self.toggle_log)\
                .grid(row=0, column=6, padx=2)
        tk.Button(self.f, text="\u26ab / \u2014", command=self.toggle_points)\
                .grid(row=0, column=7, padx=2)

        # for displaying a function of the data
        self.fn = False
        self.fn_var = tk.StringVar()
        self.fn_var.set("np.sum(y, dtype=np.int32)")
        self.x = []
        self.y = []
        tk.Button(self.f, text="f(y)", command=self.toggle_fn).grid(row=0, column=3, padx=0)
        self.fn_entry = tk.Entry(self.f, textvariable=self.fn_var)
        self.fn_clear_button = tk.Button(self.f, text="Clear", command=self.clear_fn)

        self.fft = False
        tk.Button(self.f, text="fft", command=self.toggle_fft).grid(row=0, column=4, padx=0)

    def clear_fn(self):
        """Clear the arrays of past evaluations of the custom function on the data."""
        if self.fn:
            self.x, self.y = [], []

    def toggle_fft(self):
        """
        Toggle fft for plot.
        """
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
        else:
            self.start_animation()
        # toggle the fn flag
        self.fft = not self.fft

    def toggle_fn(self):
        """Toggle controls for applying a custom function to the data."""
        # start animation and (if not yet drawn) draw plot
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
        else:
            self.start_animation()

        # toggle the fn flag
        self.fn = not self.fn

        # display/hide function controls
        if self.fn:
            self.fn_entry.grid(row=3, column=0, columnspan=6, sticky='nsew', padx=10, pady=10)
            self.fn_clear_button.grid(row=3, column=7, sticky='nsew', padx=10, pady=10)
        else:
            self.fn_entry.grid_remove()
            self.fn_clear_button.grid_remove()

    # whether to draw with just lines or also with points
    def toggle_points(self):
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)

        self.points = False if self.points==True else True

        # change marker style
        if self.points:
            self.line.set_marker('.')
        else:
            self.line.set_marker(None)

        # update plot
        self.canvas.draw()

    def toggle_log(self):
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)

        self.log = False if self.log==True else True

        # change log/lin
        if self.log:
            self.ax.set_yscale('log')
        else:
            self.ax.set_yscale('linear')

        # update plot
        self.canvas.draw()

    def start_animation(self):
        if not self.plot_drawn:
            if self.new_plot():
                self.ani.event_source.start()
        else:
            self.ani.event_source.start()
        self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
        self.animation_running = True

    def stop_animation(self):
        if self.plot_drawn:
            self.ani.event_source.stop()
        self.animation_running = False
        self.play_pause_button.configure(text="\u25b6", command=self.start_animation)

    def change_animation_dt(self, i=0, dt=-1):
        if self.plot_drawn:
            if dt > 0.1:
                self.ani.event_source.interval = 1000 * dt
            else:
                self.ani.event_source.interval = 1000 * self.dt()

    def destroy(self):
        self.f.destroy()

    def refresh_parameter_list(self, dev_name):
        self.dev_var.set(dev_name)

        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            return None

        # update the parameter list
        self.param_list = dev.config["attributes"]["column_names"].split(',')
        self.param_list = [x.strip() for x in self.param_list]
        menu = self.param_select["menu"]
        menu.delete(0, "end")
        for p in self.param_list:
            menu.add_command(label=p, command=lambda val=p: self.param_var.set(val))

        # update xcol list
        if "time" in self.param_list:
            self.xcol_list = self.param_list.copy()
        else:
            self.xcol_list = ["None"]+self.param_list.copy()
        menu = self.xcol_select["menu"]
        menu.delete(0, "end")
        for p in self.xcol_list:
            menu.add_command(label=p, command=lambda val=p: self.xcol_var.set(val))

    def get_data(self):
        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            self.stop_animation()
            messagebox.showerror("Device error", "Error: invalid device.")
            return None

        # check parameter is valid
        if ((self.param_var.get() in self.param_list) and (self.xcol_var.get() in self.xcol_list)) or \
           ((self.param_var.get() in self.param_list) and (self.xcol_var.get() == "None")):
            yparam = self.param_var.get()
            yunit = dev.config["attributes"]["units"].split(',')[self.param_list.index(yparam)]
            xparam = self.xcol_var.get()
            if xparam == "None":
                xunit = ""
                xparam = ""
            else:
                xunit = dev.config["attributes"]["units"].split(',')[self.xcol_list.index(xparam)]
        elif len(self.param_list) == 0:
            self.stop_animation()
            messagebox.showerror("Parameter error", "Error: device has no parameters.")
            return None
        else:
            # set a default parameter
            if len(self.param_list) >= 2:
                if "time" in self.param_list:
                    self.param_var.set(self.param_list[1])
                else:
                    self.param_var.set(self.param_list[0])
                self.xcol_var.set(self.xcol_list[0])
            else:
                self.param_var.set(self.param_list[0])
                self.xcol_var.set("None")
            # check the newly set parameter is valid
            if ((self.param_var.get() in self.param_list) and (self.xcol_var.get() in self.xcol_list)) or \
               ((self.param_var.get() in self.param_list) and (self.xcol_var.get() == "None")):
                yparam = self.param_var.get()
                yunit = dev.config["attributes"]["units"].split(',')[self.param_list.index(yparam)]
                xparam = self.xcol_var.get()
                if xparam == "None":
                    xunit = ""
                    xparam = ""
                else:
                    xunit = dev.config["attributes"]["units"].split(',')[self.xcol_list.index(xparam)]
            else:
                self.stop_animation()
                messagebox.showerror("Parameter error", "Error: invalid parameter.")
                return None

        # check run is valid
        try:
            with h5py.File(self.parent.config["files"]["plotting_hdf_fname"].get(), 'r') as f:
                if not self.run_var.get() in f.keys():
                    self.stop_animation()
                    messagebox.showerror("Run error", "Run not found in the HDF file.")
                    return None
        except OSError:
                self.stop_animation()
                messagebox.showerror("File error", "Not a valid HDF file.")
                return NonFalse

        # check dataset exists in the run
        with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
            try:
                grp = f[self.run_var.get() + "/" + dev.config["path"]]
            except KeyError:
                if time.time() - self.parent.config["time_offset"] > 5:
                    messagebox.showerror("Data error", "Dataset not found in this run.")
                self.stop_animation()
                return None

        # bool to check if data is sampled at a set frequency for fft
        continuous_sampling = False

        # get data
        with h5py.File(self.parent.config["files"]["hdf_fname"].get(), 'r') as f:
            grp = f[self.run_var.get() + "/" + dev.config["path"]]

            # make sure there is enough data collected to plot it
            if not dev.config["single_dataset"]:
                if len(grp) < 2:
                    self.stop_animation()
                    return None

            # if displaying a function of the data (e.g., integrated data)
            if self.fn:
                # when each acquisition is its own dataset, evaluate a
                # scalar-valued function of the latest dataset (e.g. integral of
                # entire trace plotted vs trace index)
                if not dev.config["single_dataset"]:
                    rec_num = len(grp) - 1
                    dset = grp[dev.config["name"] + "_" + str(rec_num)]
                    trace_y = dset[:, self.param_list.index(yparam)]
                    # if the most recent value hasn't been calculated yet, calculate it
                    if len(self.x) == 0 or self.x[-1] != rec_num:
                        y_fn = self.evaluate_fn(trace_y)
                        if y_fn:
                            self.x.append(rec_num)
                            self.y.append(y_fn)
                    # make sure the x, y arrays have correct shape
                    try:
                        x, y = np.array(self.x), np.array(self.y)
                    except ValueError: # else just return the trace
                        rec_num = len(grp) - 1
                        self.record_number.set(rec_num)
                        dset = grp[dev.config["name"] + "_" + str(rec_num)]
                        x = np.arange(dset.shape[0])
                        y = dset[:, self.param_list.index(yparam)]

                # when all acquisitions are in one dataset, evaluate a
                # function of individual datapoints (e.g. sqrt of the entire trace)
                else:
                    dset = grp[dev.config["name"]]
                    if self.xcol_var.get() == "None":
                        xunit = dset.attrs["sampling"].split("[")[0]
                        continuous_sampling = True
                        x = np.arange(dset.shape[0])*1/int(xunit)
                        xunit = "s"
                    else:
                        x = dset[:, self.param_list.index(self.xcol_var.get())]
                    y = self.evaluate_fn(dset[:, self.param_list.index(yparam)])

                    # check y has correct shape
                    try:
                        if isinstance(y, type(None)):
                            raise ValueError("NoneType returned")
                        elif x.shape != y.shape:
                            raise ValueError("x.shape != y.shape")
                    except ValueError as err:
                        logging.warning("Function returns invalid data: " + str(err))
                        if self.xcol_var.get() == "None":
                            xunit = dset.attrs["sampling"].split("[")[0]
                            continuous_sampling = True
                            x = np.arange(dset.shape[0])*1/int(xunit)
                            xunit = "s"
                        else:
                            x = dset[:, self.param_list.index(self.xcol_var.get())]
                        y = dset[:, self.param_list.index(yparam)]

            # if displaying data as recorded (not evaluating a function of the data)
            else:
                if dev.config["single_dataset"]:
                    try:
                        dset = grp[dev.config["name"]]
                    except KeyError as err:
                        messagebox.showerror("Data error", "Dataset not found in this run.")
                        return None
                    if self.xcol_var.get() == "None":
                        xunit = dset.attrs["sampling"].split("[")[0]
                        continuous_sampling = True
                        x = np.arange(dset.shape[0])*1/int(xunit)
                        xunit = "s"
                    else:
                        x = dset[:, self.param_list.index(self.xcol_var.get())]
                    y = dset[:, self.param_list.index(yparam)]
                else: # if each acquisition is its own dataset, return latest run only
                    rec_num = len(grp) - 1
                    self.record_number.set(rec_num)
                    dset = grp[dev.config["name"] + "_" + str(rec_num)]
                    x = np.arange(dset.shape[0])
                    y = dset[:, self.param_list.index(yparam)]

            # range of data to obtain
            try:
                i1, i2 = int(float(self.x0_var.get())), int(float(self.x1_var.get()))
            except ValueError as err:
                i1, i2 = 0, -1
            if i1 >= i2:
                if i2 >= 0:
                    i1, i2 = 0, -1
            if i2 >= dset.shape[0] - 1:
                i1, i2 = 0, -1

            # don't return more than about max_pts points
            try:
                max_pts = int(self.parent.plots.max_pts.get())
            except ValueError:
                max_pts = 10000
            dset_len = len(x)
            slice_length = (i2 if i2>=0 else dset_len+i2) - (i1 if i1>=0 else dset_len+i1)
            stride = 1 if slice_length < max_pts else int(slice_length/max_pts)
            if (self.fft) & (not self.fn) & (continuous_sampling):
                data = y[i1:i2:stride]
                fft = np.abs(np.fft.rfft(data))
                fft_freq = np.fft.rfftfreq(data.size,np.diff(x[i1:i2:stride])[0])
                return fft_freq, fft, "frequency", "", "Hz", ""
            if self.fft:
                logging.warning("Cannot perform FFT on supplied data.")
                self.toggle_fft()
            return x[i1:i2:stride], y[i1:i2:stride], xparam, yparam, xunit, yunit

    def evaluate_fn(self, data):
        fn_var = self.fn_var.get()

        # make sure the function is not empty
        if len(fn_var) == 0:
            return None

        # make sure the function contains x (the argument of function)
        if not "y" in fn_var:
            return None

        # find the requested function
        try:
            fn = lambda y : eval(fn_var)
        except (TypeError, AttributeError) as err:
            logging.warning("Cannot evaluate function: " + str(err))
            return None

        # apply the function to the data
        try:
            ret_val = fn(data)
        except (SyntaxError, AttributeError, NameError, TypeError) as err:
            logging.warning("Cannot evaluate function: " + str(err))
            return None

        return ret_val

    def new_plot(self):
        data = self.get_data()

        if data:
            x, y, xparam, yparam, xunit, yunit = data
        else:
            return False

        if self.plot_drawn:
            return False

        # draw plot
        self.fig = Figure(figsize=(6.2,2.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot(x, y)

        # labels
        if self.parent.devices[self.dev_var.get()].config["single_dataset"]:
            self.ax.set_xlabel(xparam + " [" + xunit.strip() + "]")
        else:
            self.ax.set_xlabel("sample number")
        self.ax.set_ylabel(yparam + " [" + yunit.strip() + "]")

        # plot layout
        self.fig.set_tight_layout(True)
        self.ax.grid()
        self.ax.ticklabel_format(axis='y', scilimits=(-3,3))

        # update drawing
        self.canvas = FigureCanvasTkAgg(self.fig, self.f)
        self.canvas.get_tk_widget().grid(row=4, columnspan=9)
        self.ani = animation.FuncAnimation(self.fig, self.replot,
                interval=1000*self.dt(), blit=True)
        self.ani.event_source.stop()

        ## place the plot navigation toolbar
        #t_f = tk.Frame(self.f)
        #t_f.grid(row=3, columnspan=5)
        #toolbar = NavigationToolbar2Tk(self.canvas, t_f)
        #toolbar.update()
        self.canvas._tkcanvas.grid()

        self.plot_drawn = True
        return True

    def dt(self):
        try:
            dt = float(self.dt_var.get())
        except ValueError:
            dt = 1
        if dt < 0.01:
            dt = 0.01
        return dt

    def replot(self, i=0):
        if not self.plot_drawn:
            self.new_plot()
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
            return

        data = self.get_data()

        if data:
            # update plot data
            x, y, xparam, yparam, xunit, yunit = data
            self.line.set_data(x, y)

            # update x limits
            try:
                x0, x1 = np.nanmin(x), np.nanmax(x)
                if x0 >= x1:
                    raise ValueError
            except ValueError:
                x0, x1 = 0, 1
            self.ax.set_xlim((x0, x1))

            # update y limits
            try:
                y0, y1 = float(self.y0_var.get()), float(self.y1_var.get())
                if y0 >= y1:
                    raise ValueError
            except ValueError as err:
                try:
                    y0, y1 = np.nanmin(y), np.nanmax(y)
                    if y0 == y1:
                        y0, y1 = y0 - 1, y0 + 1
                except ValueError:
                    y0, y1 = 0, 10
            try:
                self.ax.set_ylim((y0, y1))
            except ValueError as err:
                logging.warning("Cannot set ylim: " + str(err))

            # update plot labels
            if self.fn:
                self.ax.set_title(self.fn_var.get())
                if self.parent.devices[self.dev_var.get()].config["single_dataset"]:
                    self.ax.set_xlabel(xparam + " [" + xunit.strip() + "]")
                else:
                    self.ax.set_xlabel("dset number")
            else:
                if self.parent.devices[self.dev_var.get()].config["single_dataset"]:
                    self.ax.set_xlabel(xparam + " [" + xunit.strip() + "]")
                    self.ax.set_title("")
                else:
                    self.ax.set_xlabel("sample number")
                    self.ax.set_title("record #"+str(self.record_number.get()))
            self.ax.set_ylabel(yparam + " [" + yunit.strip() + "]")

            # redraw plot
            self.canvas.draw()

        return self.line,
