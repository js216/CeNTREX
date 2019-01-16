from labjack.ljm import openS, eReadName, eWriteName, eWriteNames, eStreamStart,\
                        getHandleInfo, constants, namesToAddresses, eStreamStop,\
                        eStreamRead
from labjack import ljm
import numpy as np
import time
from threading import Thread
import logging

class labjackT7:
    def __init__(self, time_offset, IP_address, sampling, channels):

        self.hv1_enable = 0
        self.hv2_enable = 0
        self.hv1 = 0
        self.hv2 = 0
        self.running_ramp = False
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
                    ("sampling", "{0} [S/s]".format(self.scans_rate))
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
        """
        Reads ADC values from the analog inputs set to streaming mode.
        """
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
        """
        Enables HV PSU 1.
        HV PSU has an inhibit input, e.g. high signal disables the PSU
        """
        name = "FIO0"
        self.DigitalIO5V(name, not enable)
        self.hv1_enable = enable

    def HV2Enable(self, enable = 0):
        """
        Enables HV PSU 1.
        HV PSU has an inhibit input, e.g. high signal disables the PSU
        """
        name = "FIO1"
        self.DigitalIO5V(name, not enable)
        self.hv2_enable = enable

    def SetPolarity(self, polarity1 = "POS", polarity2 = "NEG"):
        """
        Set polarities of HV PSU 1 & 2, requires them to be at 0 kV.
        """
        if (self.hv1 != 0) and (self.hv2 != 0):
            logging.warning("labjackT7 error: Voltages not zero, cannot switch polarities")
            return
        print(polarity1, polarity2)

    def SetHV1(self, hv1):
        """
        Set voltage of HV PSU 1.
        Sets output voltage of LJTick-DAC from 0-10 V, corresponding to 0-30kV
        """
        if not ((hv1 <= 30) & (hv1 >= 0)):
            logging.warning("labjackT7 error: Set Voltage HV1 out of range 0-30kV")
            return
        if self.hv1 == hv1:
            return
        elif not self.hv1_enable:
            logging.warning("labjackT7 error: HV1 not enabled")
            return
        elif not self.hv1 == hv1:
            print("HV1 : ",hv1)
            self.hv1 = hv1

    def SetHV2(self, hv2):
        """
        Set voltage of HV PSU 2.
        Sets output voltage of LJTick-DAC from 0-10 V, corresponding to 0-30kV
        """
        if not ((hv2 <= 30) & (hv2 >= 0)):
            logging.warning("labjackT7 error: Set Voltage HV2 out of range 0-30kV")
            return
        if self.hv2 == hv2:
            return
        elif not self.hv2_enable:
            logging.warning("labjackT7 error: HV2 not enabled")
            return
        elif not self.hv2 == hv2:
            print("HV2 : ",hv2)
            self.hv2 = hv2

    def SetVoltage(self, hv1_v, hv2_v, ramp, ramp_time):
        """
        Set voltages of HV PSU 1 & 2, capable of 0-30 kV.
        Polarity is set in another function, only possible when voltages are zero.
        """
        try:
            hv1_v = float(hv1_v)
            hv2_v = float(hv2_v)
            ramp = int(ramp)
            ramp_time = float(ramp_time)
        except Exception as e:
            logging.warning("labjackT7 error: {0}".format(e))
            return

        if (not self.hv1_enable) & (self.hv1 != hv1_v):
            logging.warning("labjackT7 error: HV1 not enabled")
            return
        if (not self.hv2_enable) & (self.hv2 != hv2_v):
            logging.warning("labjackT7 error: HV2 not enabled")
            return
        if not ((hv1_v <= 30) & (hv1_v >= 0)):
            logging.warning("labjackT7 error: Set Voltage HV1 out of range 0-30kV")
            return
        if not ((hv2_v <= 30) & (hv2_v >= 0)):
            logging.warning("labjackT7 error: Set Voltage HV2 out of range 0-30kV")
            return

        # Check if threaded ramp is already running, if yes exit SetVoltage
        if self.running_ramp:
            logging.warning("labjackT7 error: Currently running voltage ramp")
            return
        # Check if voltages are already set
        elif (self.hv1 == hv1_v) and (self.hv2 == hv2_v):
            logging.warning("labjackT7 error: Voltages already set")
        # Start threaded ramp function if ramping
        elif ramp:
            thread = Thread(target = self.RampVoltageSet, args = (hv1_v, hv2_v, ramp, ramp_time))
            thread.start()

        else:
            self.SetHV1(hv1_v)
            self.SetHV2(hv2_v)

    def RampVoltageSet(self, hv1_v, hv2_v, ramp, ramp_time):
        """
        Voltage ramping function
        """
        self.running_ramp = True
        if ramp_time == 0:
            logging.warning("labjackT7 error: Ramp time is zero")
            self.running_ramp = False
            return
        hv1_start = self.hv1
        hv2_start = self.hv2
        dv1 = hv1_v-hv1_start
        dv2 = hv2_v-hv2_start
        dt = 0.05
        dv1dt = (dv1/ramp_time)*dt
        dv2dt = (dv2/ramp_time)*dt
        steps = int(ramp_time/dt)
        for i in range(steps):
            self.SetHV1(hv1_start+dv1dt*i)
            self.SetHV2(hv2_start+dv2dt*i)
            time.sleep(dt)
        self.SetHV1(hv1_v)
        self.SetHV2(hv2_v)
        self.running_ramp = False
