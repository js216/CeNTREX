import time
import logging
import numpy as np

def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]

class HistogramPlotter:
    """
    Driver takes data from a fast device and a slow device, processes a trace
    from a fast device and subsequently bins the processed data and slow device
    data together, enabling plotting of histograms.
    """
    def __init__(self, parent, time_offset, *params):
        self.parent = parent
        self.time_offset = time_offset
        self.dev1, self.param1, self.processing, self.dev2, self.param2, \
        self.lower, self.higher, self.width = params

        # Need the " marks surrounding the expression otherwise the CeNTREX DAQ
        # enter_cmd fails due to the eval inside main, this is a workaround
        # that's only necessary on startup, to remove the quotation marks
        self.dev1 = self.Strip(self.dev1, '"')
        self.dev2 = self.Strip(self.dev2, '"')
        self.param1 = self.Strip(self.param1, '"')
        self.param2 = self.Strip(self.param2, '"')
        self.processing = self.Strip(self.processing, '"')

        # lower and higher bounds for the bin range
        self.lower = float(self.lower)
        self.higher = float(self.higher)
        # bin width
        self.width = float(self.width)

        self.verification_string = 'test'

        # lists to store matched slow (x) and processed fast (y) data in
        self.x_data = []
        self.y_data = []

        # storing a hash to ensure only new fast data is added to the histogram
        self.dev1_hash = None

        # creating the bin edges
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

    #################################################
    # Helper Functions
    #################################################

    def Strip(self, string, to_strip):
        return string.strip(to_strip)

    #################################################
    # CeNTREX DAQ Commands
    #################################################

    def GetWarnings(self):
        return []

    def ReadValue(self):
        """
        Binning the fast and slow data to enable plotting of histograms
        """
        self.ProcessData()
        x_data = self.x_data
        y_data = np.array(self.y_data)
        bins = self.bins

        # return zeros if no data present
        if (len(x_data)) == 0:
            data = np.concatenate((np.linspace(-1,1,self.shape[-1]),
                                  np.zeros(self.shape[-1]))).reshape(self.shape)
            return [data, [{'timestamp': time.time() - self.time_offset}]]

        if (len(y_data) == 0):
            data = np.concatenate((bins[:-1]+self.width/2, np.zeros(self.shape[-1]))).reshape(self.shape)
            return [data, [{'timestamp': time.time() - self.time_offset}]]

        try:
            if np.diff(bins)[0] <= 0:
                data = np.concatenate((np.linspace(-1,1,self.shape[-1]),
                                      np.zeros(self.shape[-1]))).reshape(self.shape)
                return [data, [{'timestamp': time.time() - self.time_offset}]]

            bin_indices = np.digitize(x_data, bins)
            bin_means = np.array([y_data[bin_indices == i].mean() for i in range(1,len(bins))])
            data = np.concatenate((bins[:-1]+self.width/2, bin_means)).reshape(self.shape)
            return [data, [{'timestamp': time.time() - self.time_offset}]]
        except Exception as e:
            data = np.concatenate((np.linspace(-1,1,self.shape[-1]),
                                  np.zeros(self.shape[-1]))).reshape(self.shape)
            return [data, [{'timestamp': time.time() - self.time_offset}]]
            
    def SetProcessing(self, processing):
        self.processing = processing
        self.ClearData()

    def SetDevice1(self, dev1):
        self.dev1 = dev1
        self.ClearData()

    def SetParam1(self, param1):
        self.param1 = param1
        self.ClearData()

    def SetDevice2(self, dev2):
        self.dev2 = dev2
        self.ClearData()

    def SetParam2(self, param2):
        self.param2 = param2
        self.ClearData()

    def SetLower(self, lower):
        self.lower = lower
        self.SetBins()

    def SetHigher(self, higher):
        self.higher = higher
        self.SetBins()

    def SetWidth(self, width):
        self.width = width
        self.SetBins()

    def ClearData(self):
        self.x_data = []
        self.y_data = []
        self.dev1_hash = None

    def SetBins(self):
        self.bins = np.arange(self.lower, self.higher+self.width, self.width)
        self.shape = (1, 2, len(self.bins)-1)

    #################################################
    # Device Commands
    #################################################

    def FetchData(self):
        """
        Attempting to fetch data from the specified fast and slow device.
        """
        try:
            data1 = self.parent.devices[self.dev1].config["plots_queue"][-1]
            data2 = self.parent.devices[self.dev2].config["plots_queue"][-1]
        except IndexError:
            logging.error('HistogramPlotter error in FetchData() : IndexError')
            return

        # extract the desired parameter 1 and 2
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
        """
        Processing data from the fast device
        """
        data = self.FetchData()
        if data is None:
            logging.warning('Warning in HistogramPlotter ProcessData() : no data retrieved')
            return

        y, param2_val = data

        # checking if fast device data has already been acquired before
        dev1_hash = hash(y[:10].tostring())
        if dev1_hash == self.dev1_hash:
            return
        self.dev1_hash = dev1_hash

        # evaluating the processing string supplied to __init__
        processed = eval(self.processing)

        self.x_data.append(param2_val)
        self.y_data.append(processed)
