import tkinter as tk
from tkinter import messagebox
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np

class PlotsGUI(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.place_GUI_elements()

    def place_GUI_elements(self):
        # main frame for all PlotsGUI elements
        frame = tk.Frame(self.parent.nb)
        self.parent.nb.add(frame, text="Plots")

        # button to add more plots
        add_b = tk.Button(frame, text="New plot ...")
        add_b.grid(row=0, column=0, sticky='e', padx=10)

        # place one plot
        p1_frame = tk.LabelFrame(frame, text="Plot")
        p1_frame.grid(padx=10, pady=10, sticky="nsew", row=1, column=0)
        p1 = Plotter(p1_frame, self.parent)

class Plotter(tk.Frame):
    def __init__(self, frame, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.f = frame
        self.parent = parent
        self.place_GUI_elements()

    def place_GUI_elements(self):
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

        # button to delete plot
        del_b = tk.Button(self.f, text="\u274c")
        del_b.grid(row=0, column=3, sticky='e', padx=10)

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
        replot_b = tk.Button(self.f, text="Replot", command=self.replot)
        replot_b.grid(row=1, column=3, sticky='e', padx=10)

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

    def replot(self):
        # check device is valid
        if self.dev_var.get() in self.parent.devices:
            dev = self.parent.devices[self.dev_var.get()]
        else:
            messagebox.showerror("Device error", "Error: invalid device.")
            return None

        # check parameter is valid
        param_list = dev.config["attributes"]["column_names"].split(',')
        if self.param_var.get() in param_list:
            param = self.param_var.get()
            unit = dev.config["attributes"]["units"].split(',')[param_list.index(param)]
        else:
            messagebox.showerror("Parameter error", "Error: invalid parameter.")
            return None

        # get data
        path = dev.config["current_run_dir"] + "/" + dev.config["path"] + "/"
        CSV_fname = path + dev.config["name"] + ".csv"
        data = np.loadtxt(CSV_fname, delimiter=',')
        x = data[:, 0]
        y = data[:, param_list.index(param)]

        # draw plot
        fig = Figure(figsize=(5,2.5), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot(x, y, label=param)

        # labels
        ax.set_xlabel("time [s]")
        ax.set_ylabel(param + " [" + unit.strip() + "]")

        # plot layout
        fig.tight_layout()
        ax.grid()

        # place the plot
        canvas = FigureCanvasTkAgg(fig, self.f)
        canvas.draw()
        canvas.get_tk_widget().grid(row=4, columnspan=4)

        # place the plot navigation toolbar
        t_f = tk.Frame(self.f)
        t_f.grid(row=3, columnspan=4)
        toolbar = NavigationToolbar2Tk(canvas, t_f)
        toolbar.update()
        canvas._tkcanvas.grid()


        return fig
