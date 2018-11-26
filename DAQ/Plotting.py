import tkinter as tk
from tkinter import messagebox
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.animation as animation
import numpy as np
import sys, time

from extra_widgets import VerticalScrolledFrame

class PlotsGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        # variables to keep track of the plots
        self.num_plots = 0
        self.list_of_plots = []

        # main frame for all PlotsGUI elements
        self.nb_frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(self.nb_frame, text="Plots")

        ## scrolled frame
        #fr_object = VerticalScrolledFrame(self.nb_frame)
        #self.f = fr_object.interior
        #fr_object.grid(row=0, column=0, padx=0, pady=0, sticky='nsew')

        # non-scrolled frame
        self.f = tk.Frame(self.nb_frame)
        self.f.grid(row=0, column=0, sticky='n')

        # frame for controls
        ctrls_f = tk.Frame(self.f)
        ctrls_f.grid(row=0, column=0, sticky='nsew', padx=10, pady=10)

        # button to replot all plots
        plot_b = tk.Button(ctrls_f, text="Replot all", command=self.replot_all)
        plot_b.grid(row=0, column=0, sticky='e', padx=10)

        # button to add more plots
        add_b = tk.Button(ctrls_f, text="New plot ...", command=self.add_plot)
        add_b.grid(row=0, column=1, sticky='e', padx=10)

        # add one plot
        self.add_plot()

    def replot_all(self):
        for plot in self.list_of_plots:
            plot.plot()

    def add_plot(self):
        # the plot
        self.num_plots += 1
        fr = tk.LabelFrame(self.f, text="Plot")
        fr.grid(padx=10, pady=10, sticky="nsew", row=self.num_plots, column=0)
        plot = Plotter(fr, self.parent)
        self.list_of_plots.append(plot)

        # button to delete plot
        del_b = tk.Button(fr, text="\u274c", command=lambda plot=plot: self.delete_plot(plot))
        del_b.grid(row=0, column=3, sticky='e', padx=10)

    def delete_plot(self, plot):
        plot.f.destroy()

class Plotter(tk.Frame):
    def __init__(self, frame, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.f = frame
        self.parent = parent
        self.plot_drawn = False

        # select device
        self.dev_list = [dev_name for dev_name in self.parent.devices]
        self.dev_var = tk.StringVar()
        self.dev_var.set("Select device ...")
        dev_select = tk.OptionMenu(self.f, self.dev_var, *self.dev_list,
                command=self.refresh_parameter_list)
        dev_select.grid(row=0, column=0, sticky='w')

        # select parameter
        self.param_list = ["aa", "b"]
        self.param_var = tk.StringVar()
        self.param_var.set("Select what to plot ...")
        self.param_select = tk.OptionMenu(self.f, self.param_var, *self.param_list)
        self.param_select.grid(row=0, column=1, sticky='w')

        # select between a static and dynamic plot
        self.choice = tk.StringVar()
        self.choice.set("static")
        st_rb = tk.Radiobutton(self.f, text="Static", variable=self.choice, value="static")
        st_rb.grid(row=1, column=0, sticky='w')
        dy_rb = tk.Radiobutton(self.f, text="Dynamic", variable=self.choice, value="dynamic")
        dy_rb.grid(row=2, column=0, sticky='w')

        # controls for a static plot
        self.from_var = tk.StringVar()
        self.from_var.set("from")
        from_e = tk.Entry(self.f, textvariable=self.from_var)
        from_e.grid(row=1, column=1, sticky='w')
        self.to_var = tk.StringVar()
        self.to_var.set("to")
        to_e = tk.Entry(self.f, textvariable=self.to_var)
        to_e.grid(row=1, column=2, sticky='w')
        plot_b = tk.Button(self.f, text="Plot", command=self.plot)
        plot_b.grid(row=1, column=3, sticky='e', padx=10)

        # controls for a dynamic plot
        self.dur_var = tk.StringVar()
        self.dur_var.set("duration")
        dur_e = tk.Entry(self.f, textvariable=self.dur_var)
        dur_e.grid(row=2, column=1, sticky='w')
        self.rate_var = tk.StringVar()
        self.rate_var.set("refresh rate")
        rate_e = tk.Entry(self.f, textvariable=self.rate_var)
        rate_e.grid(row=2, column=2, sticky='w')

    def refresh_parameter_list(self, dev_name):
        self.dev_var.set(dev_name)

        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            return None

        # update the parameter list
        param_list = dev.config["attributes"]["column_names"].split(',')
        menu = self.param_select["menu"]
        menu.delete(0, "end")
        for p in param_list:
            menu.add_command(label=p, command=lambda val=p: self.param_var.set(val))

        self.param_var.set(param_list[1])

    def get_data(self):
        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            messagebox.showerror("Device error", "Error: invalid device.")
            raise ValueError("invalid device")

        # check parameter is valid
        param_list = dev.config["attributes"]["column_names"].split(',')
        if self.param_var.get() in param_list:
            param = self.param_var.get()
            unit = dev.config["attributes"]["units"].split(',')[param_list.index(param)]
        else:
            messagebox.showerror("Parameter error", "Error: invalid parameter.")
            raise ValueError("invalid parameter")

        # get data
        path = dev.config["current_run_dir"] + "/" + dev.config["path"] + "/"
        CSV_fname = path + dev.config["name"] + ".csv"
        data = np.loadtxt(CSV_fname, delimiter=',')
        x = data[:, 0]
        y = data[:, param_list.index(param)]

        # cut data
        if self.choice.get() == "static":
            try:
                x1, x2 = float(self.from_var.get()), float(self.to_var.get())
                i1 = np.argmax(x>x1)
                i2 = np.argmin(x<x2) if x2<x[-1] else -1
            except ValueError as err:
                i1, i2 = 0, -1
            x, y = x[i1:i2], y[i1:i2]

        return x, y, param, unit

    def plot(self):
        if not self.plot_drawn:
            self.new_plot()
        else:
            self.replot()

    def new_plot(self):
        # obtain new data
        try:
            x, y, param, unit = self.get_data()
        except ValueError:
            return

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

        # update drawing
        self.canvas = FigureCanvasTkAgg(self.fig, self.f)
        self.canvas.get_tk_widget().grid(row=4, columnspan=4)
        self.ani = animation.FuncAnimation(self.fig, self.replot, interval=1000, blit=False)

        ## place the plot navigation toolbar
        #t_f = tk.Frame(self.f)
        #t_f.grid(row=3, columnspan=4)
        #toolbar = NavigationToolbar2Tk(self.canvas, t_f)
        #toolbar.update()
        #self.canvas._tkcanvas.grid()

        self.plot_drawn = True

    def replot(self, i=0):
        print("replot called at ", time.time())
        sys.stdout.flush()

        # obtain new data
        try:
            x, y, param, unit = self.get_data()
        except ValueError:
            return

        # update plot
        self.line.set_data(x, y)
        self.ax.set_xlim((np.min(x),np.max(x)))
        self.ax.set_ylim((np.min(y),np.max(y)))
        self.ax.set_xlabel("time [s]")
        self.ax.set_ylabel(param + " [" + unit.strip() + "]")
