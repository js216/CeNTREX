import time
import logging
import threading
import numpy as np


class MonitorSignal:
    """
    Monitoring molecular pulse signals to check if spot needs to be moved
    """
    def __init__(self, parent, time_offset, pxie, mirror, qswitch, threshold,
                 ch, nshots = 10, max_spots = 10):

        self.parent         = parent
        self.time_offset    = time_offset

        self.pxie           = pxie
        self.mirror         = mirror
        self.qswitch        = qswitch
        self.ch             = ch
        self.threshold      = threshold
        self.nshots         = nshots
        self.max_spots      = max_spots

        # storing hash to ensure only new data is checked after
        self.data_hash = [None for _ in range(nshots)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

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

    #################################################
    # CeNTREX DAQ GUI Commands
    #################################################

    def SetThreshold(self, threshold):
        self.threshold = threshold

    def GetThreshold(self):
        return self.threshold

    def SetNshots(self, nshots):
        self.nshots = nshots

    def GetNshots(self, nshots):
        return self.nshots

    def SetMaxSpots(self, max_spots):
        self.max_spots = max_spots

    def GetMaxSpots(self):
        return self.max_spots

    #################################################
    # Device Commands
    #################################################

    def FetchData(self):
        try:
            data = self.parent.devices[self.pxie].config["plots_queue"][-nshots:]
            # checking if all new retrieved shots are new data
            data_hash = [hash(d[0,0][:10].to_string()) for d in data]
            for hn, ho in zip(data_hash, self.data_hash):
                if hn == ho:
                    return -1
            self.data_hash = data_hash
        except IndexError:
            logging.error('MonitorSignal error in FetchData(): IndexError')
            return

        col_names = split(self.parent.devices[self.pxie].config["attributes"]["column_names"])
        idx = col_names.index(self.ch)
        data_l = []
        for d in data:
            data_l.append(d[0, idx].astype(float))
        return np.mean(data_l, axis = 0)

    def Checksignal(self):
        cnt = 0
        while True:
            data = self.FetchData()
            if data is None:
                logging.warning('MonitorSignal warning in ProcessData : no data retrieved')
                return
            elif data == -1:
                # not all new traces have been read out by the pxie daq yet
                continue
            integral = np.trapz(data)
            if integral > self.threshold:
                return
            else:
                self.parent.devices[self.mirror].commands.append('RandomPosition()')
                self.parent.devices[self.qswitch].commands.append(f'SetNrQswitchesGUI({self.nshots})')
                self.parent.devices[self.pxie].command.append('ReadValue()')
                cnt += 1
                if cnt == cnt_max:
                    logging.warning(f'MonitorSignal warning in ProcessData(): tried {cnt_max} spots')
