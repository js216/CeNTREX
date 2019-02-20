import tkinter as tk

from GUI import ControlGUI, MonitoringGUI, CentrexGUI

if __name__ == "__main__":
    root = tk.Tk()
    mainapp = CentrexGUI(root)
    mainapp.grid()
    root.protocol("WM_DELETE_WINDOW", mainapp.on_closing)
    root.mainloop()
