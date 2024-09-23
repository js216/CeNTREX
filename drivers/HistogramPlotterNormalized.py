import logging
import time
import traceback
from copy import copy
from typing import Dict, Sequence, Tuple, Union

import numpy as np
import numpy.typing as npt


def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]


class Histogram:
    def __init__(self, bin_edges: Union[Sequence[int], Sequence[float]]):
        self.bin_edges = bin_edges
        self.bin_centers = bin_edges[:-1] + np.diff(bin_edges) / 2

        self.data: Dict[int, Tuple[int, float]] = dict(
            [(i, (0, 0)) for i in range(1, len(bin_edges))]
        )

    def __len__(self) -> int:
        return len(self.data)

    def update(
        self,
        x: Union[npt.NDArray[np.int_], npt.NDArray[np.float_]],
        y: Union[npt.NDArray[np.int_], npt.NDArray[np.float_]],
    ):
        bin_numbers = np.digitize(x, bins=self.bin_edges, right=True)
        for bin_number in np.unique(bin_numbers):
            if bin_number == 0:
                continue
            elif bin_number >= len(self.bin_edges):
                continue
            m = bin_numbers == bin_number
            current_data = self.data.get(bin_number)
            assert current_data is not None, f"{bin_number=}, {len(self.data)=}"
            mean = (current_data[0] * current_data[1] + np.sum(y[m])) / (
                current_data[0] + m.sum()
            )
            self.data[bin_number] = (current_data[0] + m.sum(), mean)

    @property
    def x(self) -> Union[npt.NDArray[np.int_], npt.NDArray[np.float_]]:
        return self.bin_centers

    @property
    def y(self) -> Union[npt.NDArray[np.int_], npt.NDArray[np.float_]]:
        return np.array([v[1] for v in self.data.values()])


def create_bins(
    scan_values: Union[npt.NDArray[np.float_], npt.NDArray[np.int_]], maxsize: int = 100
) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
    bin_centers = np.unique(scan_values)
    if len(bin_centers) == 1:
        bins = np.array([bin_centers * 0.9, bin_centers * 1.1])
    elif len(bin_centers) > maxsize:
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
    binned_data: Histogram,
    nbins_max: int,
) -> bool:
    if len(binned_data) == 0:
        return True
    elif (x.min() < np.min(binned_data.bin_edges)) or (
        x.max() > np.max(binned_data.bin_edges)
    ):
        return True
    elif not np.all(np.isin(x, binned_data.bin_centers)) and (
        len(binned_data) < nbins_max
    ):
        return True
    else:
        return False


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
        self.x_data = []
        self.y_data = []
        self.y_data_norm = []
        self.x_data_new = []
        self.y_data_new = []
        self.y_data_norm_new = []

        self.timestamp_last_fetched = 0

        self.warnings = []
        self.new_attributes = []

        # shape and type of the array of returned data
        self.shape = (1, 2, self.nbins_max)
        self.dtype = float

        self.processed_changed = False
        self.redo_binning_flag = False

        self.binned_data: Histogram = Histogram([])

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
        # most time spent in ProcessData()
        try:
            self.ProcessData()
        except Exception as exception:
            logging.error(exception)
            logging.error(traceback.format_exc())

        x_data = np.array(self.x_data_new)
        y_data = np.array(self.y_data_new)
        y_data_norm = np.array(self.y_data_norm_new)

        # return zeros if no data present
        if len(self.x_data) < 10:
            data = np.concatenate(
                (np.linspace(-1, 1, self.shape[-1]), np.zeros(self.shape[-1]))
            ).reshape(self.shape)
            return [data, [{"timestamp": time.time() - self.time_offset}]]

        elif len(x_data) > 0:
            # check if new bins are required
            if (
                check_bins_update(
                    x_data,
                    self.binned_data,
                    self.nbins_max,
                )
                or self.redo_binning_flag
            ):
                logging.info("redo binning")
                self.redo_binning_flag = False
                self.bin_centers, self.bin_edges = create_bins(
                    self.x_data, maxsize=self.nbins_max
                )
                self.shape = (1, 2, len(self.bin_centers))
                self.binned_data = Histogram(self.bin_edges)
                self.binned_data.update(
                    np.asarray(self.x_data),
                    np.asarray(self.y_data) / np.asarray(self.y_data_norm),
                )

                self.x_data_new = []
                self.y_data_new = []
                self.y_data_norm_new = []
            else:
                self.binned_data.update(
                    x_data,
                    y_data / y_data_norm,
                )

                self.x_data_new = []
                self.y_data_new = []
                self.y_data_norm_new = []

        data = np.concatenate((self.binned_data.x, self.binned_data.y)).reshape(
            self.shape
        )

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
        self.redo_binning_flag = True
        self.nbins_max = int(nbins_max)

    def set_absorption_cutoff(self, absorption_cutoff: float):
        self.redo_binning_flag = True
        self.absorption_cutoff = absorption_cutoff

    def ClearData(self):
        self.x_data = []
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
            return [], []
        try:
            data2_queue = np.asarray(
                self.parent.devices[self.dev2].config["plots_queue"]
            )
        except KeyError:
            logging.warning(f"HistogramPlotterNorm: device {self.dev} not found")
            return [], []

        if len(data2_queue) == 0 or len(data1_queue) == 0:
            return [], []

        timestamps1 = np.asarray([d[-1][0]["timestamp"] for d in data1_queue])
        timestamps2 = np.asarray([d[0] for d in data2_queue])

        dt = timestamps2[:, np.newaxis] - timestamps1
        dt[dt > 0] = 1e3
        indices2 = np.argmin(np.abs(dt), axis=0)

        timestamps2 = timestamps2[indices2]
        data2_queue = data2_queue[indices2]

        if self.timestamp_last_fetched == 0:
            mask = np.ones(len(data1_queue), dtype=bool)
        else:
            mask = timestamps1 > self.timestamp_last_fetched
        if mask.sum() == 0:
            return [], []

        self.timestamp_last_fetched = timestamps1[mask][-1]

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
            return [], []
        try:
            idx2 = col_names2.index(self.param2)
        except IndexError:
            logging.error("Error in HistogramPlotter: param not found: " + self.param2)
            return [], []

        data1_queue = [data1_queue[idx] for idx, m in enumerate(mask) if m]

        if self.timestamp_last_fetched == 0:
            unprocessed_data = [d[0][0][idx1] for d in data1_queue]
            unprocessed_data_norm = [d[0][0][idx1norm] for d in data1_queue]
            x = [d[idx2] for d in data2_queue[mask]]
            self.x_data = copy(x)
            self.x_data_new = copy(x)
        else:
            unprocessed_data = []
            unprocessed_data_norm = []
            for idd, d in enumerate(data1_queue):
                d = d[0]
                if d.shape[0] > 1:
                    print("hit d.shape[0] > 1")
                    for di in d:
                        unprocessed_data.append(di[0][idx1])
                        unprocessed_data_norm.append(di[0][idx1norm])
                        x = data2_queue[mask][idd][idx2]
                        self.x_data.append(x)
                        self.x_data_new.append(x)
                else:
                    unprocessed_data.append(d[0][idx1])
                    unprocessed_data_norm.append(d[0][idx1norm])
                    x = data2_queue[mask][idd][idx2]
                    self.x_data.append(x)
                    self.x_data_new.append(x)
        return unprocessed_data, unprocessed_data_norm

    def ProcessData(self):
        """
        Processing data from the fast device
        """
        # most time spent in FetchData()
        unprocessed_data, unprocessed_data_norm = self.FetchData()

        if self.processed_changed:
            logging.info("processing changed")
            self.x_data = []
            self.y_data = []
            self.y_data_norm = []
            self.x_data_new = []
            self.y_data_new = []
            self.y_data_norm_new = []
            self.redo_binning_flag = True
            self.processed_changed = False
            return

        if len(self.x_data) == 0:
            return

        if len(unprocessed_data) == 0:
            return
        for idx in reversed(range(len(unprocessed_data))):
            # self.processing string contains y which is then evaluated
            y = unprocessed_data[-idx - 1]  # noqa: F841
            y_norm = unprocessed_data_norm[-idx - 1]  # noqa: F841
            yi = eval(self.processing)
            yin = eval(self.processingnorm)
            self.y_data.append(yi)
            self.y_data_norm.append(yin)
            self.y_data_new.append(yi)
            self.y_data_norm_new.append(yin)
