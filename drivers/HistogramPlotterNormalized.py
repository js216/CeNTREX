import logging
import time
from typing import Union

import numpy as np
import numpy.typing as npt
from scipy.stats import binned_statistic


def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]


def create_bins(
    scan_values: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]], maxsize: int = 100
) -> tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
    bin_centers = np.unique(scan_values)
    if len(bin_centers) > maxsize:
        bin_centers = np.linspace(bin_centers.min(), bin_centers.max(), maxsize)
        bins = bin_centers.copy()
        bin_width = bins[1] - bins[0]
        bins -= bin_width / 2
        bins = np.append(bins, bins.max() + bin_width / 2)

    else:
        dscan_min = np.diff(bin_centers).min()
        bins = np.append(
            [bin_centers.min() - dscan_min / 2],
            bin_centers + dscan_min / 2,
        )
    return bin_centers, bins


class HistogramPlotterNormalized:
    """
    Driver takes data from a fast device and a slow device, processes a trace
    from a fast device and subsequently bins the processed data and slow device
    data together, enabling plotting of histograms.
    """

    def __init__(self, parent, time_offset, *params):
        self.parent = parent
        self.time_offset = time_offset
        (
            self.dev1,
            self.param1,
            self.processing,
            self.paramnorm,
            self.processingnorm,
            self.dev2,
            self.param2,
            self.nbins_max,
        ) = params
        self.nbins_max = int(self.nbins_max)

        # Need the " marks surrounding the expression otherwise the CeNTREX DAQ
        # enter_cmd fails due to the eval inside main, this is a workaround
        # that's only necessary on startup, to remove the quotation marks
        self.dev1 = self.Strip(self.dev1, '"')
        self.dev2 = self.Strip(self.dev2, '"')
        self.param1 = self.Strip(self.param1, '"')
        self.param2 = self.Strip(self.param2, '"')
        self.processing = self.Strip(self.processing, '"')
        self.paramnorm = self.Strip(self.paramnorm, '"')
        self.processingnorm = self.Strip(self.processingnorm, '"')

        self.verification_string = "histogram_plotter"
        # lists to store matched slow (x), fast (unprocessed_data) and processed fast
        # (y) data in
        self.x_ts = []
        self.x_data = []
        self.unprocessed_data_ts = []
        self.unprocessed_data = []
        self.unprocessed_data_norm = []
        self.y_data = []

        self.warnings = []
        self.new_attributes = []

        # shape and type of the array of returned data
        self.shape = (1, 2, self.nbins_max)
        self.dtype = float

        self.processed_changed = False

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

        # return zeros if no data present
        if len(x_data) == 0 or len(y_data) == 0 or len(np.unique(x_data)) <= 1:
            data = np.concatenate(
                (np.linspace(-1, 1, self.shape[-1]), np.zeros(self.shape[-1]))
            ).reshape(self.shape)
            return [data, [{"timestamp": time.time() - self.time_offset}]]

        else:
            bin_centers, bins = create_bins(x_data, maxsize=self.nbins_max)
            self.shape = (1, 2, len(bin_centers))
            bin_means, bin_edges, bin_number = binned_statistic(
                x_data, y_data, statistic="mean", bins=bins
            )
            data = np.concatenate((bin_centers, bin_means)).reshape(self.shape)

            return [data, [{"timestamp": time.time() - self.time_offset}]]

    def SetProcessing(self, processing):
        self.processing = processing
        self.processed_changed = True

    def SetProcessingNorm(self, processingnorm):
        self.processingnorm = processingnorm
        self.processed_changed = True

    def SetDevice1(self, dev1):
        self.dev1 = dev1
        self.ClearData()

    def SetParam1(self, param1):
        self.param1 = param1
        self.ClearData()

    def SetParamNorm(self, paramnorm):
        self.paramnorm = paramnorm
        self.ClearData()

    def SetDevice2(self, dev2):
        self.dev2 = dev2
        self.ClearData()

    def SetParam2(self, param2):
        self.param2 = param2
        self.ClearData()

    def set_nbins_max(self, nbins_max: int):
        self.nbins_max = int(nbins_max)

    def ClearData(self):
        self.x_ts = []
        self.x_data = []
        self.unprocessed_data_ts = []
        self.unprocessed_data = []
        self.y_data = []
        self.unprocessed_data_norm

    #################################################
    # Device Commands
    #################################################

    def FetchData(self):
        """
        Attempting to fetch data from the specified fast and slow device.
        """
        try:
            data1_queue = self.parent.devices[self.dev1].config["plots_queue"]
        except KeyError:
            logging.warning(f"HistogramPlotterNorm: device {self.dev1} not found")
            return
        try:
            data2_queue = np.asarray(
                self.parent.devices[self.dev2].config["plots_queue"]
            )
        except KeyError:
            logging.warning(f"HistogramPlotterNorm: device {self.dev} not found")
            return

        if len(data2_queue) == 0 or len(data1_queue) == 0:
            return

        timestamps1 = np.asarray([d[-1][0]["timestamp"] for d in data1_queue])
        timestamps2 = np.asarray([d[0] for d in data2_queue])

        dt = timestamps2[:, np.newaxis] - timestamps1
        dt[dt > 0] = 1e3
        indices2 = np.argmin(np.abs(dt), axis=0)

        timestamps2 = timestamps2[indices2]
        data2_queue = data2_queue[indices2]

        if len(self.unprocessed_data) == 0:
            mask = np.ones(len(data1_queue), dtype=bool)
        else:
            mask = timestamps1 > self.unprocessed_data_ts[-1]

        # extract the desired parameter 1 and 2
        col_names1 = split(
            self.parent.devices[self.dev1].config["attributes"]["column_names"]
        )
        col_names2 = split(
            self.parent.devices[self.dev2].config["attributes"]["column_names"]
        )
        try:
            idx1 = col_names1.index(self.param1)
            idx1norm = col_names1.index(self.paramnorm)
        except IndexError:
            logging.error("Error in HistogramPlotter: param not found: " + self.param1)
            return
        try:
            idx2 = col_names2.index(self.param2)
        except IndexError:
            logging.error("Error in HistogramPlotter: param not found: " + self.param2)
            return

        self.unprocessed_data_ts = np.append(
            self.unprocessed_data_ts, timestamps1[mask]
        )
        self.x_ts = np.append(self.x_ts, timestamps2[mask])

        data1_queue = [data1_queue[idx] for idx, m in enumerate(mask) if m]
        if len(self.unprocessed_data) == 0:
            self.unprocessed_data = np.asarray(
                [d[0][0][idx1] for d in data1_queue]
            ).astype(float)
            self.unprocessed_data_norm = np.asarray(
                [d[0][0][idx1norm] for d in data1_queue]
            ).astype(float)
            self.x_data = np.asarray([d[idx2] for d in data2_queue[mask]])
        else:
            for idd, d in enumerate(data1_queue):
                # d is a list with at 0 the arrays and at 1 the timestamps
                d = d[0]
                if d.shape[0] > 1:
                    for di in d:
                        self.unprocessed_data = np.vstack(
                            [self.unprocessed_data, di[0][idx1]]
                        ).astype(float)
                        self.unprocessed_data_norm = np.vstack(
                            [self.unprocessed_data_norm, di[0][idx1norm]]
                        ).astype(float)
                        self.x_data = np.append(
                            self.x_data, data2_queue[mask][idd][idx2]
                        ).astype(float)
                else:
                    self.unprocessed_data = np.vstack(
                        [self.unprocessed_data, d[0][idx1]]
                    ).astype(float)
                    self.unprocessed_data_norm = np.vstack(
                        [self.unprocessed_data_norm, d[0][idx1norm]]
                    ).astype(float)
                    self.x_data = np.append(
                        self.x_data, data2_queue[mask][idd][idx2]
                    ).astype(float)

    def ProcessData(self):
        """
        Processing data from the fast device
        """
        self.FetchData()

        if self.processed_changed:
            self.y_data = []
            for y, y_norm in zip(self.unprocessed_data, self.processed_data_norm):
                yi = eval(self.processing)
                yin = eval(self.processingnorm)
                self.y_data.append(yi / yin)
            self.processed_changed = False
            return

        if len(self.x_data) == 0:
            return

        len_diff = len(self.unprocessed_data) - len(self.y_data)
        if len_diff == 0:
            return
        for idx in reversed(range(len_diff)):
            # self.processing string contains y which is then evaluated
            y = self.unprocessed_data[-idx - 1]
            y_norm = self.unprocessed_data_norm[-idx - 1]
            self.y_data = np.append(
                self.y_data, eval(self.processing) / eval(self.processingnorm)
            )
