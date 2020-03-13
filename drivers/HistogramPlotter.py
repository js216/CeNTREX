import time
import logging
import numpy as np

class HistogramPlotter:
    def __init__(self, parent, time_offset, *params):
        self.parent = parent
        self.time_offset = time_offset
        self.dev1, self.param1, self.processing, self.dev2, self.param2 = params

        self.x_data = []
        self.y_data = []

        self.dev1_time = 0
        self.dev2_time = 0

        self.dev1_hash = None

        self.lower = None
        self.width = None
        self.higher = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def ReadValue(self):
        self.ProcessData()
        x_data = self.x_data
        y_data = np.array(self.y_data)

        if (self.lower is None) or (self.higher is None) or (self.width is None):
            lower   = np.nanmin(y_data)
            higher  = np.nanax(y_data)
            width   = (higher - lower) / 20
        else:
            lower   = self.lower
            higher  = self.lower
            width   = self.width

        bins = np.arange(lower, higher+width, width)
        bin_indices = np.digitize(x_data, bins)
        bin_means = [y_data[bin_indices == i].mean() for i in range(1,len(bins))]
        [bins + width/2, bin_means]

    def FetchData(self):
        try:
            data1 = self.parent.devices[self.dev1].config["plots_queue"][-1]
            data2 = self.parent.devices[self.dev2].config["plots_queue"][-1]
        except IndexError:
            return

        # extract the desired parameter 1
        col_names1 = split(self.parent.devices[self.dev1].config["attributes"]["column_names"])
        col_names2 = split(self.parent.devices[self.dev2].config["attributes"]["column_names"])
        try:
            param1_dset = data[0][0, col_names1.index(self.param1)].astype(float)
        except IndexError:
            logging.error("Error in HistogramShutterPlotter: param not found: " + self.param1)
            return
        try:
            param2_val = float(latest_data[col_names2.index(self.param2)])
        except IndexError:
            logging.error("Error in HistogramShutterPlotter: param not found: " + self.param2)
            return
        return param1_dset, param2_val

    def ProcessData(self):
        y, param2_val = self.FetchData()
        dev1_hash = hash(param1_val[:10].tostring())

        if dev1_hash == self.dev1_hash:
            return

        self.dev1_hash = dev1_hash

        processed = eval(self.processing)

        self.x_data.append(param2_val)
        self.y_data.append(processed)
