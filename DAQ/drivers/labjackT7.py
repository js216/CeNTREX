from labjack.ljm import openS, eReadName, eWriteName, eWriteNames, eStreamStart,\
                        getHandleInfo, constants, namesToAddresses, eStreamStop,\
                        eStreamRead
from labjack import ljm
import numpy as np
import time
import sys
import datetime
import logging

class labjackT7:
    def __init__(self, time_offset, IP_address, sampling, channels):

        self.hv1_enable = 0
        self.hv2_enable = 0
        self.handle = openS("T7","ETHERNET",IP_address)
        self.HV1Enable()
        self.HV2Enable()
        try:
            eStreamStop(self.handle)
        except ljm.LJMError as exception:
            if exception.errorString != "STREAM_NOT_RUNNING":
                raise

        self.time_offset = time_offset

        try:
            self.verification_string = str(getHandleInfo(self.handle)[0])
        except:
            self.verification_string = "False"


        # Ensure triggered stream is disabled.
        eWriteName(self.handle, "STREAM_TRIGGER_INDEX", 0)

        # Enabling internally-clocked stream.
        eWriteName(self.handle, "STREAM_CLOCK_SOURCE", 0)

        # Configure the analog input negative channels, ranges, stream settling
        # times and stream resolution index.
        aNames = ["AIN_ALL_NEGATIVE_CH", "AIN_ALL_RANGE", "STREAM_SETTLING_US",
                  "STREAM_RESOLUTION_INDEX"]
        aValues = [constants.GND, 10.0, 0, 0]  # single-ended, +/-10V, 0 (default), 0 (default)
        eWriteNames(self.handle, len(aNames), aNames, aValues)

        # start acquisition
        self.active_channels = []
        self.active_channel_names = []
        for ch in [0,1,2,3,4,5]:
            if bool(int(channels[0][ch].get())):
                self.active_channel_names.append(channels[1][ch].get())
                self.active_channels.append("AIN{0}".format(ch))
        self.num_addresses = len(self.active_channels)
        self.scan_list = namesToAddresses(self.num_addresses, self.active_channels)[0]
        self.scans_rate = int(sampling["scans_rate"].get())
        self.scans_per_read = int(sampling["scans_per_read"].get())

        self.new_attributes = [
                    ("column_names", ", ".join(self.active_channel_names)),
                    ("units", ", ".join(["V"]*len(self.active_channels))),
                    ("scans_rate", "{0} [S/s]".format(self.scans_rate))
               ]

        # shape and type of the array of returned data
        self.shape =  (self.num_addresses,)
        self.dtype = 'f'

        self.scan_rate = eStreamStart(self.handle, self.scans_per_read,
                                      self.num_addresses, self.scan_list,
                                      self.scans_rate)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            eStreamStop(self.handle)
        except ljm.LJMError as exception:
            if exception.errorString != "STREAM_NOT_RUNNING":
                raise
        ljm.close(self.handle)

    def GetWarnings(self):
        return None

    def ReadValue(self):
        # the structures for reading waveform data into
        data = np.array(eStreamRead(self.handle)[0]).reshape(-1,self.num_addresses)
        return data

    def DigitalIO5V(self, name, high):
        """
        Labjack digital IO is 3.3V, need 5V for the HV PSU. Use open-collector
        style to get 5V from 3.3V with a pullup to a 5V source.
        Set the line to input for 5V out.
        Set the line to output-low for 3.3V out.
        """
        if high:
            eReadName(self.handle, name)
        else:
            eWriteName(self.handle, name, 0)

    def HV1Enable(self, enable = 0):
        # HV enable works as an inhibit; e.g. high signal disables HV
        name = "FIO0"
        self.DigitalIO5V(name, not enable)
        self.hv1_enable = enable

    def HV2Enable(self, enable = 0):
        # HV enable works as an inhibit; e.g. high signal disables HV
        name = "FIO1"
        self.DigitalIO5V(name, not enable)
        self.hv2_enable = enable

    def SetPolarity(self, polarity1 = "POS", polarity2 = "NEG"):
        print(polarity1, polarity2)

    def SetVoltage(self, hv1_v, hv2_v, ramp, ramp_time):
        print(hv1_v, hv2_v, ramp, ramp_time)
