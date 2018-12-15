import tkinter as tk
from tkinter import messagebox
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.animation as animation
import numpy as np
import sys, time
import csv
import gc

from extra_widgets import VerticalScrolledFrame

class PlotsGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        # variable to keep track of the plots
        self.all_plots = {}

        # main frame for all PlotsGUI elements
        self.nb_frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.nb_frame, text="Plots")

        ## vertically scrolled frame
        #fr_object = VerticalScrolledFrame(self.nb_frame)
        #self.f = fr_object.interior
        #fr_object.grid(row=0, column=0, padx=0, pady=0, sticky='nsew')

        # non-scrolled frame
        self.f = tk.Frame(self.nb_frame)
        self.f.grid(row=0, column=0, sticky='n')

        # controls for all plots
        ctrls_f = tk.Frame(self.f)
        ctrls_f.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)
        tk.Button(ctrls_f, text="Start all", command=self.start_all)\
                .grid(row=0, column=0, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Stop all", command=self.stop_all)\
                .grid(row=0, column=1, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Replot all", command=self.replot_all)\
                .grid(row=0, column=2, sticky='e', padx=10)
        tk.Button(ctrls_f, text="Delete all", command=self.delete_all)\
                .grid(row=0, column=3, sticky='e', padx=10)

        # button to add add plot in the specified column
        self.col_var = tk.StringVar()
        self.col_var.set("col")
        tk.Entry(ctrls_f, textvariable=self.col_var).grid(row=0, column=4, sticky='w', padx=10)
        add_b = tk.Button(ctrls_f, text="New plot ...", command=self.add_plot)
        add_b.grid(row=0, column=5, sticky='e', padx=10)

        # add one plot
        self.add_plot()

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

    def replot_all(self):
        for col, col_plots in self.all_plots.items():
            for row, plot in col_plots.items():
                if plot:
                    plot.replot()

    def add_plot(self):
        # find location for the plot
        try:
            col = int(self.col_var.get())
        except ValueError:
            col = 0
        row = max([ r for r in self.all_plots.setdefault(col, {0:None}) ]) + 1

        # frame for the plot
        fr = tk.LabelFrame(self.f, text="Plot")
        fr.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

        # place the plot
        plot = Plotter(fr, self.parent)
        self.all_plots[col][row] = plot

        # button to delete plot
        del_b = tk.Button(plot.ctrls_f, text="\u274c", command=lambda plot=plot,
                row=row, col=col: self.delete_plot(row,col,plot))
        del_b.grid(row=0, column=7, sticky='e', padx=10)

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

        # select device
        self.dev_list = [dev_name.strip() for dev_name in self.parent.devices]
        self.dev_var = tk.StringVar()
        self.dev_var.set("Select device ...")
        dev_select = tk.OptionMenu(self.f, self.dev_var, *self.dev_list,
                command=self.refresh_parameter_list)
        dev_select.grid(row=0, column=0, columnspan=2, sticky='w')

        # select parameter
        self.param_list = [""]
        self.param_var = tk.StringVar()
        self.param_var.set("Select what to plot ...")
        self.param_select = tk.OptionMenu(self.f, self.param_var, *self.param_list)
        self.param_select.grid(row=0, column=2, columnspan=2, sticky='w')

        # plot range controls
        self.x0_var = tk.StringVar()
        self.x0_var.set("x0")
        tk.Entry(self.f, textvariable=self.x0_var, width=6)\
                .grid(row=1, column=0, sticky='w', padx=4)
        self.x1_var = tk.StringVar()
        self.x1_var.set("x1")
        tk.Entry(self.f, textvariable=self.x1_var, width=6)\
                .grid(row=1, column=1, sticky='w', padx=4)
        self.y0_var = tk.StringVar()
        self.y0_var.set("y0")
        tk.Entry(self.f, textvariable=self.y0_var, width=6)\
                .grid(row=1, column=2, sticky='w', padx=4)
        self.y1_var = tk.StringVar()
        self.y1_var.set("y1")
        tk.Entry(self.f, textvariable=self.y1_var, width=6)\
                .grid(row=1, column=3, sticky='w', padx=4)

        # control buttons
        self.ctrls_f = tk.Frame(self.f)
        self.ctrls_f.grid(row=0, column=4, sticky='nsew', padx=10)
        self.f.columnconfigure(3, weight=1)
        self.ctrls_f.columnconfigure(7, weight=1)
        self.dt_var = tk.StringVar()
        self.dt_var.set("plot refresh rate [s]")
        dt_entry = tk.Entry(self.ctrls_f, textvariable=self.dt_var)
        dt_entry.grid(row=1, column=0, columnspan=3, sticky='w')
        dt_entry.bind("<Return>", self.change_animation_dt)
        tk.Button(self.ctrls_f, text="Plot", command=self.replot)\
                .grid(row=0, column=0, sticky='e', padx=2)
        self.play_pause_button = tk.Button(self.ctrls_f, text="\u25b6", command=self.start_animation)
        self.play_pause_button.grid(row=0, column=1, sticky='e', padx=2)
        tk.Button(self.ctrls_f, text="Log/Lin", command=self.toggle_log)\
                .grid(row=0, column=2, sticky='e', padx=2)
        tk.Button(self.ctrls_f, text="\u26ab / \u2014", command=self.toggle_points)\
                .grid(row=0, column=3, sticky='e', padx=2)

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
        if self.new_plot():
            self.ani.event_source.start()
        else:
            self.ani.event_source.start()
        self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)

    def stop_animation(self):
        if not self.new_plot():
            self.ani.event_source.stop()
        self.play_pause_button.configure(text="\u25b6", command=self.start_animation)

    def change_animation_dt(self, i=0):
        if self.plot_drawn:
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

        self.param_var.set(self.param_list[1])

    def get_data(self):
        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            messagebox.showerror("Device error", "Error: invalid device.")
            return None

        # check parameter is valid
        if self.param_var.get() in self.param_list:
            param = self.param_var.get()
            unit = dev.config["attributes"]["units"].split(',')[self.param_list.index(param)]
        else:
            messagebox.showerror("Parameter error", "Error: invalid parameter.")
            return None

        # get filename of the data file
        CSV_fname = dev.config["current_run_dir"] + "/" + dev.config["path"] \
                + "/" + dev.config["name"] + ".csv"

        # range of data to obtain
        try:
            i1, i2 = int(self.x0_var.get()), int(self.x1_var.get())
        except ValueError as err:
            i1, i2 = 0, -1
        if i1 >= i2:
            if i2 >= 0:
                i1, i2 = 0, -1

        # get data
        try:
            data = np.loadtxt(CSV_fname, delimiter=',')
        except OSError:
            return None

        # check if any data returned
        if len(data.shape) < 2:
            return None

        # cut and return data
        x = data[:, 0]
        y = data[:, self.param_list.index(param)]
        if i2 <= len(x):
            x, y = x[i1:i2], y[i1:i2]
        return x, y, param, unit

    def new_plot(self):
        data = self.get_data()

        if data:
            x, y, param, unit = data
        else:
            return False

        if self.plot_drawn:
            return False

        # draw plot
        self.fig = Figure(figsize=(5.5,2.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot(x, y)

        # labels
        self.ax.set_xlabel("time [s]")
        self.ax.set_ylabel(param + " [" + unit.strip() + "]")

        # plot layout
        self.fig.tight_layout()
        self.ax.grid()
        self.ax.ticklabel_format(axis='y', scilimits=(-3,3))

        # update drawing
        self.canvas = FigureCanvasTkAgg(self.fig, self.f)
        self.canvas.get_tk_widget().grid(row=4, columnspan=6)
        self.ani = animation.FuncAnimation(self.fig, self.replot, interval=self.dt(), blit=False)
        self.ani.event_source.stop()

        ## place the plot navigation toolbar
        t_f = tk.Frame(self.f)
        t_f.grid(row=3, columnspan=5)
        toolbar = NavigationToolbar2Tk(self.canvas, t_f)
        toolbar.update()
        self.canvas._tkcanvas.grid()

        self.plot_drawn = True
        return True

    def dt(self):
        try:
            dt = float(self.dt_var.get())
        except ValueError:
            dt = 1
        if dt < 0.1:
            dt = 1
        return dt

    def replot(self, i=0):
        if self.new_plot():
            self.play_pause_button.configure(text="\u23f8", command=self.stop_animation)
            return

        if self.plot_drawn:
            data = self.get_data()
        else:
            return

        if data:
            x, y, param, unit = data
            self.line.set_data(x, y)
            self.ax.set_xlim((np.nanmin(x),np.nanmax(x)))
            try:
                y0, y1 = float(self.y0_var.get()), float(self.y1_var.get())
                if y0 > y1:
                    raise ValueError
            except ValueError as err:
                y0, y1 = np.nanmin(y), np.nanmax(y)
            self.ax.set_ylim((y0, y1))
            self.ax.set_xlabel("time [s]")
            self.ax.set_ylabel(param + " [" + unit.strip() + "]")
            self.canvas.draw()
