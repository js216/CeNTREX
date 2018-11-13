"""
According to the [MKS website](https://www.mksinst.com/docs/UR/pin1179a.aspx),
the pinout for the 9-pin Type "D" Connector is as follows:

| Pin | Description        |
|-----|--------------------|
| 1   | Valve Open/Close   |
| 2   | Flow Signal Output |
| 3   | +15 VDC            |
| 4   | Power Common       |
| 5   | -15 VDC            |
| 6   | Set Point Input    |
| 7   | Signal Common      |
| 8   | Signal Common      |
| 9   | MKS Test Point     |

Let's represent the instrument as a Python object. Each of the functions implied
by the above pinout table becomes a member method of the Python object. Each of
these methods sets up a DAQ task to perform the operation.

As the hardware interface consists of the channels of a NI USB-6008 connected in
some way to the 9-pin D-sub connector of the MKS 1179C, the constructor of the
`MKS1179C` class needs to be told what pin of the DAQ device corresponds to
which one on the mass-flow controller. We do this by passing a list of names of
DAQ inputs connected to pins 1, 2, and 6 of the 1179C.

Note that the control commands are executed hierarhcically. For example, "if
the flow controller is operating under Set Point Control, you can send a Valve
Open command to force the valve to the full open position." [[1179A
manual]](https://www.mksinst.com/docs/r/1179A-2179A-179Aman.pdf)
"""

import PyDAQmx
import numpy as np

class MKS1179C:
    def __init__(self, valve_chan, flow_signal_out, setpoint_in):
        self.valve_chan      = valve_chan
        self.flow_signal_out = flow_signal_out
        self.setpoint_in     = setpoint_in

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        pass
    
    #################################################################
    ##########              READ COMMANDS                  ##########
    #################################################################
    
    def ReadFlowSignal(self):
        flow = PyDAQmx.float64()
        with PyDAQmx.Task() as task:
            task.CreateAIVoltageChan(self.flow_signal_out,"",
                PyDAQmx.DAQmx_Val_Cfg_Default, 0.0, 5.0,
                PyDAQmx.DAQmx_Val_Volts,None)
            task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
            task.StartTask()
            task.ReadAnalogScalarF64(1.0, PyDAQmx.byref(flow), None)
        return float(str(flow)[9:-1])
        
    #################################################################
    ##########              CONTROL COMMANDS               ##########
    #################################################################
        
    def ValveOpen(self):
        with PyDAQmx.Task() as task:
            task.CreateDOChan(self.valve_chan, "",
                              PyDAQmx.DAQmx_Val_ChanPerLine)
            task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
            task.StartTask()
            task.WriteDigitalLines(1, True, 1.0,
                PyDAQmx.DAQmx_Val_GroupByChannel,
                np.array([1], dtype=np.uint8),
                None, None)
            
    def ValveClose(self):
        with PyDAQmx.Task() as task:
            task.CreateDOChan(self.valve_chan, "",
                              PyDAQmx.DAQmx_Val_ChanPerLine)
            task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
            task.StartTask()
            task.WriteDigitalLines(1, True, 1.0,
                PyDAQmx.DAQmx_Val_GroupByChannel,
                np.array([0], dtype=np.uint8),
                None, None)
            
    def SetPointControl(self, setpoint):
        """Set setpoint in volts (5 volts max)."""
        if setpoint > 5:
            raise ValueError("Setpoint too high.")
        with PyDAQmx.Task() as task:
            task.CreateAOVoltageChan(self.setpoint_in, "", 0.0, 5.0,
                PyDAQmx.DAQmx_Val_Volts,None)
            task.SetSampTimingType(PyDAQmx.DAQmx_Val_OnDemand)
            task.StartTask()
            task.WriteAnalogScalarF64(True, 1.0, setpoint, None)
