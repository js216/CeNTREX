import visa
import numpy as np

class Tektronix2014B:
    def __init__(self, resource_manager, resource_name):
        self.rm = resource_manager
        self.instr = self.rm.open_resource(resource_name)
        self.instr.timeout = 5000 # reading data can be slow

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.instr.close()

    #################################################################
    ##########  Convenience functions                      ##########
    #################################################################

    def get_waveform(self, channel):
        # select channel
        self.instr.write('data:source '+channel)

        # select the encoding (see above note on data representation)
        self.instr.write('data:encdg SRIBINARY')

        # select 16-bit (2-byte) precision
        self.instr.write('data:width 2')

        # get the entire waveform
        self.instr.write('data:start 1')
        self.instr.write('data:stop 2500')

        # read a part of the waveform preamble
        [_, _, _, _, _, _, wfid, _,
         xincr, pt_off, xzero, xunit,
         ymult, yzero, yoff, yunit] = \
            self.instr.query('WFMPre?').split(';')

        # transfer waveform data
        self.instr.write('curv?')
        WFMdata = self.instr.read_raw()
        curve = np.frombuffer(WFMdata[6:-1], dtype=np.int16)

        # convert into physical units (see manual, p2-250 / PDFp270)
        x = float(xzero)+float(xincr)*(np.arange(2500)-float(pt_off))
        y = float(yzero)+float(ymult)*(curve-float(yoff))

        return [x, y, xunit, yunit]

    #################################################################
    ##########  Measurement functions                      ##########
    #################################################################
    ## The best method for taking measurements over the computer   ##
    ## interface is to use the MEASUREMENT:IMMED commands and      ##
    ## queries. The immediate measurement has no front-panel       ##
    ## equivalent, and the oscilloscope never displays immediate   ##
    ## measurements. Because they are computed only when they are  ##
    ## requested, immediate measurements slow the waveform update  ##
    ## rate less than displayed measurements.                      ##
    ## Use the VALue? query to obtain measurement results of       ##
    ## either displayed or immediate measurements.                 ##
    #################################################################

    def AllMeasParams(self):
        """Return all measurement parameters."""
        return self.instr.query('measurement?')

    def ImmedMeasParams(self):
        """Return immediate measurement parameters."""
        return self.instr.query('measurement:immed?')

    def QueryImmedMeasChan(self):
        """Query the channel for immediate measurement."""
        return self.instr.query('measurement:immed:source1?')

    def SetImmedMeasChan(self, chan):
        """Set the channel for immediate measurement."""
        self.instr.write('measurement:immed:source1 '+chan)

    def QueryImmedMeas2Chan(self):
        """Set or query the channel for two-source immediate measurements
           (TPS2000 with Power Analysis Module only)."""
        return self.instr.query('measurement:immed:source2?')

    def SetImmedMeasChan(self, chan):
        """Set the channel for two-source immediate measurements
           (TPS2000 with Power Analysis Module only)."""
        self.instr.write('measurement:immed:source2 '+chan)

    def QueryImmedMeasType(self):
        """Query the immediate measurement to be taken."""
        return self.instr.query('measurement:immed:type?')

    def SetImmedMeasType(self, meas_type):
        """Set the immediate measurement to be taken.
        
        FREQuency is the reciprocal of the period measured in Hertz.

        MEAN is the arithmetic mean over the entire waveform.

        PERIod is the duration, in seconds, of the first complete cycle in the
        waveform.

        PK2pk is the absolute difference between the maximum and
        minimum amplitude.

        CRMs is the true Root Mean Square voltage of the first complete
        cycle in the waveform.

        MINImum (TDS1000, TDS2000, TDS1000B, TDS2000B, and
        TPS2000 series only) is the value of the smallest point in the
        waveform.

        MAXImum (TDS1000, TDS2000, TDS1000B, TDS2000B, and
        TPS2000 series only) is the value of the largest point in the
        waveform.

        RISe ( TDS200 series with a TDS2MM measurement module,
        TDS1000, TDS2000, TDS1000B, TDS2000B, and TPS2000 series
        only) is the rise time between 10% and 90% of the first rising edge
        of the waveform. Rising edge must be displayed to measure. The
        oscilloscope automatically calculates the 10% and 90% measurement
        points.

        FALL (TDS200 series with a TDS2MM measurement module,
        TDS1000, TDS2000, TDS1000B, TDS2000B, and TPS2000 series
        only) is the fall time between 90% and 10% of the first falling edge
        of the waveform. Falling edge must be displayed to measure. The
        oscilloscope automatically calculates the 10% and 90% measurement
        points.

        PWIdth (TDS200 series with a TDS2MM measurement module,
        TDS1000, TDS2000, TDS1000B, TDS2000B, and TPS2000 series
        only) is the positive pulse width between the first rising edge and the
        next falling edge at the waveform 50% level. Rising and falling
        edges must be displayed to measure. The oscilloscope automatically
        calculates the 50% measurement point.

        NWIdth (TDS200 series with a TDS2MM measurement module,
        TDS1000, TDS2000, TDS1000B, TDS2000B, and TPS2000 series
        only) is the negative pulse width between the first falling edge and
        the next rising edge at the waveform 50% level. Falling and rising
        edges must be displayed to measure. The oscilloscope automatically
        calculates the 50% measurement point.

        WFCREST (TPS2000 series with TPS2PWR1 Power Analysis Module
        only) is the measurement of the maximum value to the cycle RMS
        value of the waveform, a unit-less ratio.

        WFFREQ (TPS2000 series with TPS2PWR1 Power Analysis Module
        only) is the measurement of frequency using the min-max, high-low
        method.

        WFCYCRMS (TPS2000 series with TPS2PWR1 Power Analysis Module
        only) is the measurement of RMS voltage calculated over the first
        cycle, using the min-max, high-low method.

        TRUEPOWER (TPS2000 series with TPS2PWR1 Power Analysis
        Module only) is the true power measurement in Watts. Source 1 must
        be volts; source 2 must be Amperes.

        VAR (TPS2000 series with TPS2PWR1 Power Analysis Module only)
        is the reactive power measurement. Source 1 must be volts; source 2
        must be Amperes.

        POWERFACTOR (TPS2000 series with TPS2PWR1 Power Analysis
        Module only) is the true power factor ratio measurement. Source 1
        must be volts; source 2 must be Amperes.

        PFPHASE (TPS2000 series with TPS2PWR1 Power Analysis Module
        only) is the phase angle measurement in degrees. Source 1 must be
        volts; source 2 must be Amperes.

        PHAse (TPS2000 series with TPS2PWR1 Power Analysis Module
        only) is the measurement of phase between source 1 and source 2, in
        degrees.
        """
        self.instr.write('measurement:immed:type '+meas_type)

    def QueryImmedMeasUnits(self):
        """Return the immediate measurement units."""
        return self.instr.query('measurement:immed:units?')

    def QueryImmedMeasValue(self):
        """Return the immediate measurement result."""
        return float( self.instr.query('measurement:immed:value?').strip('\n') )

    def QueryPerMeasParams(self, meas):
        """Return parameters on the periodic measurement."""
        return self.instr.query('measurement:meas'+str(meas)+'?')

    def QueryPerMeasChan(self, meas):
        """Query the channel to take the periodic measurement from."""
        return self.instr.query('measurement:meas'+str(meas)+':source?')

    def SetPerMeasChan(self, meas, chan):
        """Set the channel to take the periodic measurement from."""
        self.instr.write('measurement:meas'+str(meas)+':source '+chan)

    def QueryPerMeasType(self, meas):
        """Query the type of periodic measurement to be taken."""
        return self.instr.query('measurement:meas'+str(meas)+':type?')

    def SetPerMeasChan(self, meas, meas_type):
        """Set the type of periodic measurement to be taken."""
        self.instr.write('measurement:meas'+str(meas)+':type '+meas_type)

    def QueryPerMeasUnits(self, meas):
        """Return the units for periodic measurement."""
        return self.instr.query('measurement:meas'+str(meas)+':units?')

    def QueryPerMeasValue(self, meas):
        """Return periodic measurement results."""
        return self.instr.query('measurement:meas'+str(meas)+':value?')

    #################################################################
    ##########  Acquisition functions                      ##########
    #################################################################
    ## NOTE. While Trigger View is active (when you push the TRIG  ##
    ## VIEW button on the front panel), the oscilloscope ignores   ##
    ## the set form of most commands. If you send a command at     ##
    ## this time, the oscilloscope generates execution error 221   ##
    ## (Settings conflict).                                        ##
    #################################################################

    def QueryAcqParams(self):
        """Return acquisition parameters."""
        return self.instr.query('acquire?')

    def QueryAcqMode(self):
        """Query the acquisition mode."""
        return self.instr.query('acquire:mode?')

    def SetAcqMode(self, meas_mode):
        """Set the acquisition mode.

        Arguments:

        SAMple specifies that the displayed data point value is the first
        sampled value that was taken during the acquisition interval. The
        waveform data has 8 bits of precision in all acquisition modes. You
        can request 16 bit data with a CURVe? query, but the lower-order
        8 bits of data will be zero. SAMple is the default mode.

        PEAKdetect specifies the display of the high-low range of the
        samples taken from a single waveform acquisition. The oscilloscope
        displays the high-low range as a vertical range that extends from the
        highest to the lowest value sampled during the acquisition interval.
        PEAKdetect mode can reveal the presence of aliasing.

        AVErage specifies averaging mode, where the resulting waveform
        shows an average of SAMple data points from several separate
        waveform acquisitions. The number of waveform acquisitions that
        go into making up the average waveform is set or queried using the
        ACQuire:NUMAVg command.
        """
        self.instr.write('acquire:mode '+meas_mode)

    def QueryAcqNumAcq(self):
        """Return the # of acquisitions obtained."""
        return self.instr.query('acquire:numacq?')

    def QueryAcqNumAvg(self):
        """Query the number of acquisitions for average."""
        return self.instr.query('acquire:numavg?')

    def SetAcqNumAvg(self, num):
        """Set the number of acquisitions for average.
        
        Arguments:
            
        <NR1> is the number of waveform acquisitions.
        Correct values are 4, 16, 64, and 128.
        """
        self.instr.write('acquire:numavg '+str(num))

    def QueryAcqState(self):
        """Query the start/stop state of the acquisitions system."""
        return self.instr.query('acquire:state?')

    def SetAcqState(self, state):
        """Start or stop the acquisition system.
        
        This command is the equivalent of pressing the front-panel RUN/STOP
        button. If ACQuire:STOPAfter is set to SEQuence, other signal events may
        also stop acquisition.

        NOTE. The best way to determine when a single sequence acquisition is
        complete is to use *OPC? rather than ACQuire:STATE?. For more
        information on the *OPC? command, refer to manual pages 2--169.

        Arguments:

        OFF | STOP | <NR1> = 0 stops acquisitions.

        ON | RUN | <NR1> != 0 starts acquisition and display of waveforms. If
        the command was issued in the middle of an acquisition sequence (for
        instance averaging), RUN restarts the sequence, discarding any data
        accumulated before the STOP. It also resets the number of acquisitions.
        """
        self.instr.write('acquire:state '+state)

    def QueryAcqCtrl(self):
        """Query the acquisition control."""
        return self.instr.query('acquire:stopafter?')

    def SetAcqCtrl(self, ctrl):
        """Tells the oscilloscope when to stop taking acquisitions.

        Arguments: RUNSTop specifies that the run and stop states should be
        determined by pressing the front-panel RUN/STOP button or issuing the
        ACQuire:STATE command

        SEQuence specifies "single sequence" operation, where the oscilloscope
        stops after it has acquired enough waveforms to satisfy the conditions
        of the acquisition mode. For example, if the acquisition mode is set to
        sample, the oscilloscope stops after digitizing a waveform from a single
        trigger event.  However, if the acquisition mode is set to average 64
        waveforms, then the oscilloscope stops only after acquiring all 64
        waveforms.
        
        The ACQuire:STATE command and the front-panel RUN/STOP button also stop
        acquisitions when the oscilloscope is in single sequence mode.
        """
        self.instr.write('acquire:stopafter '+ctrl)

# Implemented commands:
# ----------------------------
# Acquisition commands
# Measurement Commands

# Commands not yet implemented here:
# ----------------------------
# Calibration and Diagnostic Commands
# Cursor Commands
# Display Commands
# File System Commands (TDS2MEM Module, TDS1000B, TDS2000B, and TPS2000 Only)
# Hard Copy Commands
# Horizontal Commands
# Math Commands
# Miscellaneous Commands
# PictBridge Commands (TDS1000B and TDS2000B Only)
# Power and Battery-Related Commands (TPS2000 Only)
# Power Measurement (TPS2000 with TPS2PWR1 Power Analysis Application Key Installed Only)
# RS-232 Commands
# Save and Recall Commands
# Status and Error Commands
# Trigger Commands
# Vertical Commands
# Waveform Commands
