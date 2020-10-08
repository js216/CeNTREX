import time
import logging
import numpy as np

def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]

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
        self.threshold      = float(threshold)
        self.nshots         = int(nshots)
        self.max_spots      = int(max_spots)

        # storing hash to ensure only new data is checked after
        self.data_hash = [None for _ in range(nshots)]

        self.latest_integral = np.nan

        self.new_attributes = []

        self.shape = (2,)
        self.dtype = ('f', 'float')

        self.warnings = []

        self.verification_string = 'True'

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
        return [time.time()-self.time_offset, self.latest_integral]

    #################################################
    # CeNTREX DAQ GUI Commands
    #################################################

    def SetThreshold(self, threshold):
        self.threshold = float(threshold)

    def GetThreshold(self):
        return self.threshold

    def SetNshots(self, nshots):
        if int(nshots) < 1:
            logging.warning(f'MonitorSignal warning in SetNshots : invalid nr shots specified ({nshots})')
        self.nshots = int(nshots)

    def GetNshots(self):
        return self.nshots

    def SetMaxSpots(self, max_spots):
        self.max_spots = int(max_spots)

    def GetMaxSpots(self):
        return self.max_spots

    #################################################
    # Device Commands
    #################################################

    def FetchData(self):
        try:
            data = []
            for idx in range(self.nshots+1,0,-1):
                d = self.parent.devices[self.pxie].config["plots_queue"][-idx][0]
                data.append(d)
            data = np.array(data)

            # checking if all new retrieved shots are new data
            data_hash = [hash(d[0,0][:10].tostring()) for d in data]
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

    def CheckSignal(self, rate = 25):
        max_loops = 100
        loops = 0
        spots = 0
        while True:
            loops += 1
            if loops == max_loops:
                logging.warning('MonitorSignal warning in CheckSignal : maximum tries exceeded')
                return
            data = self.FetchData()
            if data is None:
                logging.warning('MonitorSignal warning in CheckSignal : no data retrieved')
                return
            if not isinstance(data, np.ndarray):
                if np.isnan(data):
                    logging.warning('MonitorSignal warning in CheckSignal : no data retrieved')
                    return
                elif data == -1:
                    # not all new traces have been read out by the pxie daq yet
                    continue
                else:
                    logging.warning('MonitorSignal warning in CheckSignal : invalid data retrieved')
                    return
            integral = np.trapz(-(data - np.mean(data[:250])))
            self.latest_integral = integral
            if integral > self.threshold:
                return
            else:
                self.parent.devices[self.mirror].commands.append('RandomPosition()')
                self.parent.devices[self.qswitch].commands.append(f'SetNrQswitchesGUI({self.nshots})')
                for _ in range(self.nshots):
                    self.parent.devices[self.pxie].commands.append('ReadValue()')
                time.sleep(2*self.nshots*(1/rate))
                spots += 1
                if spots == self.max_spots:
                    logging.warning(f'MonitorSignal warning in ProcessData(): tried {self.max_spots} spots')
                    return
