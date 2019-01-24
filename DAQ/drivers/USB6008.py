"""
This is the driver for the NI-USB 6008 device, which controls the MKS 1179C mass
flow controller, as well as the flood detector.
"""

import PyDAQmx
import numpy as np
import time

class USB6008:
    def __init__(self, time_offset, flow_signal_out, setpoint_in, flood_in, flood_out):
        self.time_offset = time_offset
        self.flow_signal_out = flow_signal_out
        self.setpoint_in     = setpoint_in
        self.flood_in        = flood_in
        self.flood_out       = flood_out

        self.setpoint        = 0.0

        # make the verification string
        try:
            self.ReadFlowSignal()
            self.verification_string = "operational"
        except:
            self.verification_string = "cannot read"

        if not self.SetPointControl(self.setpoint):
            self.verification_string = "cannot set setpoint"

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (3, )

        # for flood checking
        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def ReadValue(self):
        return [time.time()-self.time_offset, self.ReadFlowSignal(), self.setpoint_sccm]

    def GetWarnings(self):
        self.AutoCheckFlood()
        warnings = self.warnings
        self.warnings = []
        return warnings

    #################################################################
    ##########              READ COMMANDS                  ##########
    #################################################################

    def ReadFlowSignal(self):
        flow = PyDAQmx.float64()
        with PyDAQmx.Task() as task:
            task.CreateAIVoltageChan(
                    physicalChannel       = "/Dev1/ai0",
                    nameToAssignToChannel = "",
                    terminalConfig        = PyDAQmx.DAQmx_Val_RSE,
                    minVal                = 0.0,
                    maxVal                = 1.0,
                    units                 = PyDAQmx.DAQmx_Val_Volts,
                    customScaleName       = None)
            task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
            task.StartTask()
            task.ReadAnalogScalarF64(1.0, PyDAQmx.byref(flow), None)

        # calculate the flow rate from voltage
        flow_signal = float(str(flow)[9:-1])
        return flow_signal / 5 * 100

    def CheckFlood(self):
        """Check for flooding of the compressor cabinet.

        Flood sensor is a relay that is closed in normal operation and open when
        a flood is detected. This function applies a high and a low signal to
        one terminal of the relay and checks that the corresponding signal
        appears on the other terminal.
        """
        for test_val in [0, 1]:
            # write test_val to port0/line1
            with PyDAQmx.Task() as task:
                task.CreateDOChan(self.flood_out, "", PyDAQmx.DAQmx_Val_ChanPerLine)
                task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
                task.StartTask()
                task.WriteDigitalLines(1, True, 1.0, PyDAQmx.DAQmx_Val_GroupByChannel,
                        np.array([test_val], dtype=np.uint8), None, None)

                # read back the value from port0/line0
            with PyDAQmx.Task() as task:
                task.CreateDIChan(self.flood_in, "", PyDAQmx.DAQmx_Val_ChanForAllLines)
                task.StartTask()
                data = np.zeros(1, dtype=np.uint32)
                task.ReadDigitalU32(numSampsPerChan = -1, 
                        timeout = 1.0,
                        fillMode = PyDAQmx.DAQmx_Val_GroupByChannel,
                        readArray = data,
                        arraySizeInSamps = len(data),
                        sampsPerChanRead = PyDAQmx.byref(PyDAQmx.int32()),
                        reserved=None)

                # check that the read value matches the written value
            if test_val != data[0]:
                return "flooding"
            return "no flood"

    def ManualCheckFlood(self):
        flood = self.CheckFlood()
        warning_dict = { "message" : flood }
        if flood == "no flood":
            warning_dict["is_flooding"] = 0
        elif flood == "flooding":
            warning_dict["is_flooding"] = 1
        self.warnings.append([time.time(), warning_dict])
        return flood

    def AutoCheckFlood(self):
        flood = self.CheckFlood()
        if flood == "no flood":
            return None
        else:
            warning_dict = {
                    "message" : flood,
                    "is_flooding" : 1,
                }
            self.warnings.append([time.time(), warning_dict])

    #################################################################
    ##########              CONTROL COMMANDS               ##########
    #################################################################

    def SetPointControl(self, setpoint_sccm):
        # calculate the setpoint voltage from sccm
        self.setpoint_sccm = setpoint_sccm
        self.setpoint_V = self.setpoint_sccm / 100 * 5

        # check for too high a setpoint
        if self.setpoint > 100:
            raise ValueError("Setpoint too high.")

        # set setpoint
        with PyDAQmx.Task() as task:
            task.CreateAOVoltageChan(self.setpoint_in, "", 0.0, 5.0,
                PyDAQmx.DAQmx_Val_Volts,None)
            task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
            task.StartTask()
            try:
                task.WriteAnalogScalarF64(True, 1.0, self.setpoint_V, None)
            except PyDAQmx.DAQmxFunctions.PALUSBTransactionErrorError as err:
                return str(err)
            else:
                return True
