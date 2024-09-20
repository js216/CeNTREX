import logging
import time
from typing import Dict, Tuple, Union

import numpy as np
import numpy.typing as npt
from scipy.stats import binned_statistic


def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]


def create_bins(
    scan_values: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]], maxsize: int = 100
) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
    bin_centers = np.unique(scan_values)
    if len(bin_centers) > maxsize:
        bin_centers = np.linspace(bin_centers.min(), bin_centers.max(), maxsize)
        bins = bin_centers.copy()
        bin_width = bins[1] - bins[0]
        bins -= bin_width / 2
        bins = np.append(bins, bins.max() + bin_width / 2)

    else:
        bin_diffs = np.diff(bin_centers)
        bins = np.append(
            [bin_centers[0] - bin_diffs[0] / 2], bin_centers[1:] - bin_diffs / 2
        )
        bins = np.append(bins, [bin_centers[-1] + bin_diffs[-1] / 2])
    return bin_centers, bins


def check_bins_update(
    x: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]],
    binned_data: Dict[int, Tuple[int, float]],
    bin_centers: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]],
    bin_edges: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]],
    nbins_max: int,
) -> bool:
    if len(binned_data) == 0:
        return True
    elif (x.min() < np.min(bin_edges)) or (x.max() > np.max(bin_edges)):
        return True
    elif not np.all(np.isin(x, bin_centers)) and (len(binned_data) < nbins_max):
        return True
    else:
        return False


def bin_new_data(
    x_data: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]],
    y_data: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]],
    binned_data: Dict[int, Tuple[int, float]],
    bin_edges: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]],
) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
    bin_numbers = np.digitize(x_data, bins=bin_edges, right=True)
    for bin_number in np.unique(bin_numbers):
        if bin_number == 0:
            continue
        m = bin_numbers == bin_number
        current_data = binned_data.get(bin_number)
        if current_data is None:
            binned_data[bin_number] = (m.sum(), np.mean(y_data[m]))
        else:
            # calculate the new mean of the data
            mean = (current_data[0] * current_data[1] + np.sum(y_data[m])) / (
                current_data[0] + m.sum()
            )
            binned_data[bin_number] = (current_data[0] + m.sum(), mean)
    return


class HistogramPlotter:
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
            self.dev2,
            self.param2,
            self.nbins_max,
        ) = params

        self.nbins_max = int(self.nbins_max)
        self.bin_width = int(self.bin_width)

        # Need the " marks surrounding the expression otherwise the CeNTREX DAQ
        # enter_cmd fails due to the eval inside main, this is a workaround
        # that's only necessary on startup, to remove the quotation marks
        self.dev1 = self.Strip(self.dev1, '"')
        self.dev2 = self.Strip(self.dev2, '"')
        self.param1 = self.Strip(self.param1, '"')
        self.param2 = self.Strip(self.param2, '"')
        self.processing = self.Strip(self.processing, '"')

        self.verification_string = "histogram_plotter"

        # lists to store matched slow (x), fast (unprocessed_data) and processed fast
        # (y) data in
        self.x_ts = []
        self.x_data = []
        self.unprocessed_data_ts = []
        self.unprocessed_data = []
        self.y_data = []
        self.x_data_new = []
        self.y_data_new = []
        self.warnings = []
        self.new_attributes = []

        # shape and type of the array of returned data
        self.shape = (1, 2, self.nbins_max)
        self.dtype = float

        self.processed_changed = False

        self.binned_data: Dict[int, Tuple[int, float]] = {}
        self.bin_centers = None
        self.bin_edges = None
        self.shape = None

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
        try:
            self.ProcessData()
        except Exception as exception:
            logging.error(exception)

        x_data = self.x_data_new
        y_data = np.array(self.y_data_new)

        # return zeros if no data present
        if len(x_data) == 0 or len(y_data) == 0 or len(np.unique(x_data)) <= 1:
            data = np.concatenate(
                (np.linspace(-1, 1, self.shape[-1]), np.zeros(self.shape[-1]))
            ).reshape(self.shape)
            return [data, [{"timestamp": time.time() - self.time_offset}]]

        else:
            # check if new bins are required
            if check_bins_update(
                x_data,
                self.binned_data,
                self.bin_centers,
                self.bin_edges,
                self.nbins_max,
            ):
                self.bin_centers, self.bin_edges = create_bins(
                    self.x_data, maxsize=self.nbins_max
                )
                self.shape = (1, 2, len(self.bin_centers))
                self.binned_data.clear()
                bin_new_data(self.x_data, self.y_data, self.binned_data, self.bin_edges)
            else:
                bin_new_data(x_data, y_data, self.binned_data, self.bin_edges)

            bin_means = np.array([v[1] for v in self.binned_data.values()])
            data = np.concatenate((self.bin_centers, bin_means)).reshape(self.shape)

            return [data, [{"timestamp": time.time() - self.time_offset}]]

    def SetProcessing(self, processing):
        self.processing = processing

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

    def set_nbins_max(self, nbins_max: int):
        self.nbins_max = int(nbins_max)

    def ClearData(self):
        self.x_ts = []
        self.x_data = []
        self.unprocessed_data_ts = []
        self.unprocessed_data = []
        self.y_data = []

    #################################################
    # Device Commands
    #################################################

    def FetchData(self):
        """
        Attempting to fetch data from the specified fast and slow device.
        """
        try:
            data1_queue = list(self.parent.devices[self.dev1].config["plots_queue"])
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
        except IndexError:
            logging.error("Error in HistogramPlotter: param not found: " + self.param1)
            return
        try:
            idx2 = col_names2.index(self.param2)
        except IndexError:
            logging.error("Error in HistogramPlotter: param not found: " + self.param2)
            return

        self.unprocessed_data_ts.extend(timestamps1[mask])
        self.x_ts.extend(timestamps2[mask])

        data1_queue = [data1_queue[idx] for idx, m in enumerate(mask) if m]
        if len(self.unprocessed_data) == 0:
            self.unprocessed_data = [d[0][0][idx1] for d in data1_queue]
            x = [d[idx2] for d in data2_queue[mask]]
            self.x_data = x
            self.x_data_new = x
        else:
            for idd, d in enumerate(data1_queue):
                # d is a list with at 0 the arrays and at 1 the timestamps
                d = d[0]
                if d.shape[0] > 1:
                    self.x_data_new = []
                    for di in d:
                        self.unprocessed_data.append(di[0][idx1])
                        x = data2_queue[mask][idd][idx2]
                        self.x_data.append(x)
                        self.x_data_new.append(x)
                else:
                    self.unprocessed_data.append(d[0][idx1])
                    x = data2_queue[mask][idd][idx2]
                    self.x_data.append(x)
                    self.x_data_new = x

    def ProcessData(self):
        """
        Processing data from the fast device
        """
        self.FetchData()

        if self.processed_changed:
            self.y_data = []
            for y in self.unprocessed_data:
                self.y_data.append(eval(self.processing))
            self.processed_changed = False
            return

        if len(self.x_data) == 0:
            return

        len_diff = len(self.unprocessed_data) - len(self.y_data)
        if len_diff == 0:
            return
        for idx in reversed(range(len_diff)):
            # self.processing string contains y which is then evaluated
            y = self.unprocessed_data[-idx - 1]  # noqa: F841
            y = eval(self.processing)
            self.y_data.append(y)
            self.y_data_new = y
