import time
import logging
import numpy as np

def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]

class HistogramPlotter:
    def __init__(self, parent, time_offset, *params):
        self.parent = parent
        self.time_offset = time_offset
        self.dev1, self.param1, self.processing, self.dev2, self.param2, \
        self.lower, self.higher, self.width = params
        self.lower = float(self.lower)
        self.higher = float(self.higher)
        self.width = float(self.width)

        self.verification_string = 'test'

        self.x_data = []
        self.y_data = []

        self.dev1_time = 0
        self.dev2_time = 0

        self.dev1_hash = None

        self.bins = np.arange(self.lower, self.higher+self.width, self.width)

        self.warnings = []
        self.new_attributes = []

        # shape and type of the array of returned data
        self.shape = (1, 2, len(self.bins)-1)
        self.dtype = np.float

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def GetWarnings(self):
        return []

    def ReadValue(self):
        self.ProcessData()
        x_data = self.x_data
        y_data = np.array(self.y_data)
        if (len(x_data) == 0) or (len(y_data) == 0):
            return np.nan
        bins = self.bins

        bin_indices = np.digitize(x_data, bins)
        bin_means = np.array([y_data[bin_indices == i].mean() for i in range(1,len(bins))])
        data = np.concatenate((bins[:-1]+self.width/2, bin_means)).reshape(self.shape)
        return [data, [{'timestamp': time.time() - self.time_offset}]]

    def FetchData(self):
        try:
            data1 = self.parent.devices[self.dev1].config["plots_queue"][-1]
            data2 = self.parent.devices[self.dev2].config["plots_queue"][-1]
        except IndexError:
            logging.error('HistogramPlotter error in FetchData() : IndexError')
            return

        # extract the desired parameter 1
        col_names1 = split(self.parent.devices[self.dev1].config["attributes"]["column_names"])
        col_names2 = split(self.parent.devices[self.dev2].config["attributes"]["column_names"])
        try:
            param1_dset = data1[0][0, col_names1.index(self.param1)].astype(float)
        except IndexError:
            logging.error("Error in HistogramShutterPlotter: param not found: " + self.param1)
            return
        try:
            param2_val = float(data2[col_names2.index(self.param2)])
        except IndexError:
            logging.error("Error in HistogramShutterPlotter: param not found: " + self.param2)
            return
        return param1_dset, param2_val

    def ProcessData(self):
        data = self.FetchData()
        if data is None:
            logging.warning('Warning in HistogramPlotter ProcessData() : no data retrieved')
            return

        y, param2_val = data
        dev1_hash = hash(y[:10].tostring())

        if dev1_hash == self.dev1_hash:
            return

        self.dev1_hash = dev1_hash

        processed = eval(self.processing)

        self.x_data.append(param2_val)
        self.y_data.append(processed)
