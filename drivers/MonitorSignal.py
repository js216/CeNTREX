import time
import logging
import threading
import numpy as np


class MonitorSignal:
    """
    Monitoring molecular pulse signals to check if spot needs to be moved
    """
    def __init__(self, parent, time_offset, pxie, mirror, qswitch, threshold,
                 ch, nshots = 10, max_spots = 50):

        self.parent         = parent
        self.time_offset    = time_offset

        self.pxie           = pxie
        self.mirror         = mirror
        self.qswitch        = qswitch
        self.ch             = ch
        self.threshold      = threshold
        self.nshots         = nshots
        self.max_spots      = max_spots


    def __exit__(self, *exc):
        return

    def __enter__(self):
        return self

    #######################################################
    # CeNTREX DAQ Commands
    #######################################################
    def CreateWarning(self, warning):
        warning_dict = { "message" : warning}
        self.warnings.append([time.time(), warning_dict])

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        return [time.time()-self.time_offset]

    def FetchData(self):
        try:
            data = self.parent.devices[self.pxie].config["plots_queue"][-nshots:]
        except IndexError:
            logging.error('MonitorSignal error in FetchData(): IndexError')
            return

        col_names = split(self.parent.devices[self.pxie].config["attributes"]["column_names"])
        idx = col_names.index(self.ch)
        data_l = []
        for d in data:
            data_l.append(d[0, idx].astype(float))
        return np.mean(data_l, axis = 0)

    def ProcessData(self):
        cnt = 0
        while True:
            data = self.FetchData()
            integral = np.trapz(data)
            if integral > threshold:
                return
            else:
                self.parent.devices[self.pxie].commands.append('RandomPosition()')
                self.parent.devices[self.qswitch].commands.append(f'SetNrQswitchesGUI({self.nshots})')
                cnt += 1
                if cnt == cnt_max:
                    logging.warning(f'MonitorSignal warning in ProcessData(): tried {cnt_max} spots')
