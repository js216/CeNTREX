import pyvisa
import datetime as dt
import functools
import numpy as np
import time
from contextlib import contextmanager
from influxdb import InfluxDBClient
import logging

def QueryVisaIOError(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in {0}() : '.format(func.__name__) \
                            +str(err))
            return np.nan
    return wrapper

def WriteVisaIOError(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in {0}() : '.format(func.__name__) \
                            +str(err))
    return wrapper

class FS740:
    def __init__(self, time_offset, resource_name, protocol = 'RS232'):
        self.rm = pyvisa.ResourceManager()
        if protocol == 'RS232':
            self.instr = self.rm.open_resource(resource_name)
            self.instr.parity = pyvisa.constants.Parity.none
            self.instr.data_bits = 8
            self.instr.write_termination = '\r\n'
            self.instr.read_termination = '\r\n'
            self.instr.baud_rate = 115200
        elif protocol == 'TCP':
            self.instr = self.rm.open_resource("TCPIP::{0}::5025::SOCKET".format(resource_name))
            self.instr.write_termination = '\r\n'
            self.instr.read_termination = '\r\n'

        self.time_offset = time_offset

        self.verification_string = self.VerifyOperation()
        if not isinstance(self.verification_string, str):
            self.verification_string = False
        self.new_attributes = []
        self.dtype = 'f16'
        self.shape = (6,)

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.instr.close()

    def query(self, cmd):
        return self.instr.query(cmd)

    def write(self, cmd):
        self.instr.write(cmd)

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def ReadValue(self):
        self.WriteValueINFLUXDB()
        return [
                time.time() - self.time_offset,
                float(self.TBaseStateLockDuration()),
                float(self.TBaseTInterval()),
                float(self.TBaseTInterval(True)),
                float(self.QueryTBaseTConstant()),
                float(self.QueryTBaseFControl()),
        ]

    def ReadValueINFLUXDB(self, full_output = False):
        date = self.QuerySystemDate()
        time =  self.QuerySystemTime()
        time_alig = self.QueryGPSConfigAlignment()
        tbase_state = self.TBaseState()
        tbase_hold_dur = int(self.TBaseStateHoldoverDuration())
        tbase_warm_dur = int(self.TBaseStateWarumpDuration())
        tbase_lock_dur = int(self.TBaseStateLockDuration())
        fcontrol = float(self.QueryTBaseFControl())
        hmode = self.QueryTBaseConfigHMode()
        bwidth = self.QueryTBaseConfigBWidth()
        lock = bool(self.QueryTBaseConfigLock())
        tint_lim = float(self.QueryTBaseConfigTIntervalLimit())
        tint = float(self.TBaseTInterval())
        tint_avg = float(self.TBaseTInterval(average = True))
        tconstant_cur = int(self.QueryTBaseTConstant())
        tconstant_tar = int(self.QueryTBaseTConstant("TARG"))
        gps_pos = self.GPSPosition()
        gps_track = self.GPSSatelliteTracking()
        gps_track_state = self.GPSSatelliteTrackingStatus()
        gps_mode = self.QueryGPSConfigMode()
        gps_qual = self.QueryGPSConfigQuality()
        gps_adelay = float(self.QueryGPSConfigADelay())
        values = (date, time, time_alig, tbase_state, tbase_hold_dur,
                  tbase_warm_dur, tbase_lock_dur, fcontrol, hmode, bwidth, lock,
                  tint_lim, tint, tint_avg, tconstant_cur, tconstant_tar, gps_pos,
                  gps_mode, gps_qual, gps_adelay, gps_track, gps_track_state)
        desc = ('SystemDate', 'SystemTime', 'GPSAlignment', 'TBaseState',
                'TBaseHoldDuration', 'TBaseWarmDuration', 'TBaseLockDuration',
                'TBaseFControl', 'TBaseHMode', 'TBaseBWidth', 'TBaseLock',
                'TBaseTIntervalLimit', 'TBaseTInterval', 'TBaseTIntervalAverage',
                'TBaseTConstantCurrent', 'TBaseTConstantTarget', 'GPSPosition',
                'GPSMode', 'GPSQuality', 'GPSADelay', 'GPSSatelliteTracking',
                'GPSSatelliteTrackingStatus')
        if full_output:
            return values, desc
        else:
            return values

    @staticmethod
    def ExpandValue(values, desc, label, conv, labels):
        idx = desc.index(label)
        val = values[idx].split(',')
        val = [c(v) for c,v in zip(conv,val)]
        values = list(values)
        del values[idx]
        values[idx:idx] = val
        desc = list(desc)
        del desc[idx]
        desc[idx:idx] = labels
        return values, desc

    @staticmethod
    def chunks(l,n):
        lst = []
        for i in range(0, len(l), n):
            lst.append(l[i:i+n])
        return lst

    def WriteValueINFLUXDB(self):
        """
        I've now hardcoded in the influxdb part because I already made a
        database in a different way than Jakob has it setup for the general
        acquisition software.
        Should transition over at some point.
        """
        @contextmanager
        def get_connection(*args, **kwargs):
            connection = InfluxDBClient(*args, **kwargs)
            try:
                yield connection
            finally:
                connection.close()

        tableO, tableS, tableL = 'overview', 'satellites', 'log'

        values, descs = self.ReadValueINFLUXDB(full_output = True)

        s = values[1].split('.')
        time = dt.datetime.strptime(values[0]+' '+s[0]+'.'+s[1][:6],
                                    '%Y,%m,%d %H,%M,%S.%f').isoformat()

        values, descs = self.ExpandValue(values, descs, 'GPSMode',
                                         (bool, float, float), ('antiJamming',
                                         'elevationMask','signalMask'))
        values, descs = self.ExpandValue(values, descs, 'GPSPosition',
                                         (float, float, float),
                                         ('latitude', 'longitude', 'altitude'))

        idx = descs.index('GPSSatelliteTrackingStatus')
        sats = self.chunks(values[idx].split(','), 8)
        ids, signal, elevation, azimuth = \
        zip(*[(int(val[0]), int(val[4]), int(val[5]), int(val[6]))
              for val in sats if (val[3] =='0') and (val[0] != '0')])

        values = values[2:-2]
        descs = descs[2:-2]
        values.append(len(ids))
        descs.append("satelitesConnected")
        values.append(round(sum(signal)/len(signal),1))
        descs.append('SNR')

        writeO = {"measurement":tableO,
                 "tags": {'clock_id':'FS740'},
                 "time":time,
                 "fields":dict((key,value) for key,value in
                               zip(descs,values))}

        writeS = [{"measurement":tableS,
                  "tags":{'satelliteID':id},
                  "time":time,
                  "fields":{"signal":sig,
                            "elevation":ele,
                            "azimuth":azi}} for id, sig, ele, azi in \
                  zip(ids, signal, elevation, azimuth)]

        writeL = []
        while int(self.TBaseEventCount()) > 0:
            event = self.TBaseEventNext().split(',')
            msg = event[0]
            ts = ','.join(event[1:])
            ts = dt.datetime.strptime(ts,"%Y,%m,%d,%H,%M,%S").isoformat()
            writeL.append({"measurement":tableL,
                           "tags":{"deviceID":'FS740', "label":"event"},
                           "time":ts, "fields":{"message":msg}})
        with get_connection(host = '172.28.82.114', port = 8086,
                            database = 'clock', username = 'test', \
                            password = 'test') as connection:
            connection.write_points([writeO])
            connection.write_points(writeS)
            if len(writeL) > 0:
                connection.write_points(writeL)

    def VerifyOperation(self):
        return self.QueryIDN().split(',')[1]

    #################################################################
    ##########  Common IEEE-448.2 Commands                 ##########
    #################################################################

    def CLS(self):
        """
        This command immediately clears all status registers as well
        as the SYST:ERR queue.
        Manual p.91
        """
        try:
            self.write("*CLS")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in CLS() : '+str(err))
            return np.nan

    def ESE(self, value):
        """
        Set the Standard Event Status Enable register to <value>. The
        value may range from 0 to 255. Bits set in this register cause
        ESR (in *STB) to be set when the corresponding bit is set in
        the *ESR register.
        Manual p.91
        """
        try:
            self.write("*ESE {0}".format(value))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in ESE() : '+str(err))
            return np.nan

    def QueryESE(self):
        try:
            return self.query("*ESE?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryESE() : '+str(err))
            return np.nan

    def QueryESR(self):
        """
        Query the Standard Event Status Register. After the query,
        the returned bits of the *ESR register are cleared. The bits
        in the ESR register have the following meaning:

        bit : name : meaning
        0   : OPC  : operation complete
        1   :      :
        2   : QYE  : Query error occured
        3   : DDE  : Device dependent error occured
        4   : EXE  : Excecution error. Command failed to execute
                     correctly because a parameter was invalid
        5   : CME  : Command error. The parser detected a syntax
                     error.
        6   :      :
        7   : PON  : Power on. The unit has been power cycled.
        """
        try:
            return self.query("*ESR?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryESR() : '+str(err))
            return np.nan

    def QueryOPC(self):
        """
        The set form sets the OPC flag in the *ESR register when all
        prior commands have completed. The query form returns ‘1’ when
        all prior commands have completed, but does not affect the
        *ESR register.
        Manual p.92
        """
        try:
            return self.query("*OPC?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryOPC() : '+str(err))
            return np.nan

    def QueryOPT(self):
        """
        The query returns a comma separated list of the four possible
        installed options in the following order: installed timebase,
        top rear panel board, middle rear panel board, and bottom rear
        panel board.

        type     : option   : value
        Timebase : TCXO     : 0
                 : OCXO     : 1
                 : Rb       : 2
        Board    : 10 MHz   : A
                 : Sine/Aux : B
                 : Pulse    : C
                 : None     : D
        Manual p.92

        2,A,A,A -> Rb timebase, 3x 10 MHz distribution slots.
        """
        try:
            return self.query("*OPT?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryOPT() : '+str(err))
            return np.nan

    def QueryIDN(self):
        """
        Query the instrument identification string.
        Manual p.92
        """
        try:
            return self.query("*IDN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryIDN() : '+str(err))
            return np.nan

    def PSC(self, value):
        """
        Set the Power-on Status Clear flag to <value>. The Power-on
        Status Clear flag is stored in nonvolatile memory in the unit,
        and thus, maintains its value through power-cycle events. If
        the value of the flag is 0, then the Service Request Enable
        and Standard Event Status Enable Registers (*SRE, *ESE) are
        stored in non-volatile memory, and retain their values through
        powercycle events. If the value of the flag is 1, then these
        two registers are cleared upon power-cycle.
        Manual p.93
        """
        try:
            self.write("*PSC {0}".format(value))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in PSC() : '+str(err))
            return np.nan

    def QueryPSC(self):
        try:
            return self.query("*PSC?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryPSC() : '+str(err))
            return np.nan

    def RCL(self, location):
        """
        Recall instrument settings from <location>. The <location> may
        range from 0 to 9. Locations 1 to 9 are for arbitrary use.
        Location 0 is reserved for the recall of default instrument
        settings.
        Manual p.93
        """
        if not isinstance(location, int):
            logging.warning("FS740 warning in RCL() : location invalid type")
        if (location >= 0 ) & (location <= 9):
            logging.warning("FS740 warning in RCL() : location out of range")
        try:
            self.write("*RCL {0}".format(location))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in RCL() : '+str(err))
            return np.nan

    def RST(self):
        """
        Reset the instrument to default settings. This is equivalent
        to *RCL 0.
        Manual p.93
        """
        try:
            self.write("*RST")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in RST() : '+str(err))
            return np.nan

    def SRE(self, value):
        """
        Set the Service Request Enable register to <value>. Bits set
        in this register cause the FS740 to generate a service request
        when the corresponding bit is set in the serial poll status
        register, *STB.
        Manual p.94
        """
        try:
            self.write("*SRE {0}".format(value))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SRE() : '+str(err))
            return np.nan

    def QuerySRE(self):
        try:
            return self.query("*SRE?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySRE() : '+str(err))
            return np.nan

    def QuerySTB(self):
        """
        Query the standard IEEE 488.2 serial poll status byte. The bits
        in the STB register have the following meaning:

        bit : meaning
        0   : reserved
        1   : GPS status summary bit
        2   : Error queue is not empty
        3   : Questionable status summary bit
        4   : Message available, MAV
        5   : ESR status summary bit
        6   : MSS master summary bit
        7   : Operational status summary bit

        Manual p.94
        """
        try:
            return self.query("*STB?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySTB() : '+str(err))
            return np.nan

    def SAV(self, location):
        """
        Save instrument settings to <location>. The <location> may
        range from 0 to 9. However, location 0 is reserved for
        current instrument settings. It will be overwritten after each
        front panel key press.
        Manual p.93
        """
        if not isinstance(location, int):
            logging.warning("FS740 warning in SAV() : location invalid type")
        if not ((location >= 0) and (location <= 9)):
            logging.warning("FS740 warning in SAV() : location out of range")
        try:
            self.write("*SAV {0}".format(location))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SAV() : '+str(err))
            return np.nan

    def WAI(self):
        """
        The instrument will not process further commands until all
        prior commands including this one have completed.
        Manual p.95
        """
        try:
            self.write("*WAI")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in WAI() : '+str(err))
            return np.nan

    #################################################################
    #######  Measurement commands                             #######
    #################################################################

    @staticmethod
    def ValidateFrequency(freq):
        if freq in ['DEF', 'MIN', 'MAX']:
            return True
        if not isinstance(freq, (int, float)):
            logging.warning("FS740 warning in ValidateFrequency() : " +
                             "freq invalid type")
            return False
        if not ((freq >= 1e-1) and (freq <= 1.5e8)):
            logging.warning("FS740 warning in ValidateFrequency() : " +
                             "freq out of range")
            return False
        return True

    @staticmethod
    def ValidateResolution(res):
        if res in ['DEF', 'MIN', 'MAX']:
            return
        if not isinstance(res, int):
            logging.warning("FS740 warning in ValidateResolution() : \
                             res invalid type")
            return
        if not ((res >= 1e-16) and (res <= 1.5e-2)):
            logging.warning("FS740 warning in ValidateResolution() : \
                             res out of range")

    def MeasureFrequency(self, expected = 'DEF', resolution = 'DEF',
                          front = True):
        """
        Configures hardware for a frequency measurement and
        immediately triggers a measurement and sends the result to the
        output buffer. The first parameter is optional and informs the
        instrument of the expected frequency of the signal. The second
        parameter is also optional. It sets the requested resolution
        of the measurement. Neither parameter is used directly by the
        FS740. Instead the ratio of the resolution to the expected
        frequency is used to set the gate time for the measurement. If
        the parameters are omitted, a gate time of 0.1 second is used
        which corresponds to approximately 11 digits of precision.
        Measurements are returned as floating point values in units of
        Hz. If ameasurement times out NAN is returned.
        Manual p.96
        """
        if not self.ValidateFrequency(expected):
            logging.warning("FS740 warning in MeasureFrequency() : \
                             expected invalid")
            return np.nan
        if not self.ValidateResolution(resolution):
            logging.warnign("FS740 warning in MeasureFrequency() : \
                             resolution invalid")
            return np.nan
        try:
            return self.query("MEAS{0}:FREQ? {1}, {2}".format(
                1 if front else 2, expected, resolution))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in MeasureFrequency() : '+str(err))
            return np.nan

    def MeasureTime(self, front = True):
        """
        Trigger default time measurement
        Manual p.96
        """
        try:
            return self.query("MEAS{0}:TIM?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in MeasureTime() : '+str(err))
            return np.nan

    def QueryConfigure(self, front = True):
        """
        Read current measurement configuration.
        Manual p.97
        """
        try:
            return self.query("CONF{0}?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryConfigure() : '+str(err))
            return np.nan

    def ConfigureFrequency(self, freq = 'DEF', res = 'DEF',
                           front = True):
        """
        Configure hardware for frequency measurement.
        Manual p.97
        """
        if not self.ValidateFrequency(freq):
            logging.warning("FS740 warning in ConfigureFrequency() : \
                             freq invalid")
            return np.nan
        if not self.ValidateResolution(res):
            logging.warnign("FS740 warning in ConfigureFrequency() : \
                             res invalid")
            return np.nan
        try:
            self.write("CONF{0}:FREQ {1}, {2}".format(1 if front else 2,
                                                   freq, res))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in ConfigureFrequency() : '+str(err))
            return np.nan

    def ConfigureTime(self, front = True):
        """
        Configures hardware for a measurement of time and immediately
        triggers a measurement and sends the result to the output buffer.
        Results are returned with a READ command. A single result consists
        of 11 comma separated integer values in the following order:
        timing metric, year, month, day, hour, minute, seconds,
        milliseconds, microseconds, nanoseconds, picoseconds. The timing
        metric is a copy of the questionable status register at the time
        of the measurement.
        Manual p.98
        """
        try:
            self.write("CONF{0}:TIM".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in ConfigureTime() : '+str(err))
            return np.nan


    def Read(self, front = True):
        """
        Trigger a measurement using the current configuration and read
        the result. See commands MEASure:FREQuency and MEASure:TIMe for
        details on the format of results returned. When the sample size
        is greater than one, results are separated from each other by
        commas ( , ).
        Manual p.98
        """
        try:
            return self.query("READ{0}?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Read() : '+str(err))
            return np.nan

    def Initiate(self, front = True):
        """
        Trigger a measurement using the current configuration but
        leave results in internal memory. The internal memory has
        enough space to store the last 250,000 measurements. The
        user should send the FETCh command to retrieve the results
        from internal memory. Alternatively, the user may use commands
        in the DATA subsystem to read only a portion of the results.
        Manual p.98
        """
        try:
            self.write("INIT{0}".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Initiate() : '+str(err))
            return np.nan

    def Fetch(self, front = True):
        """
        Copy results stored in the internal buffer to the output buffer
        for reading. Like the READ command, this command will not
        complete until all measurements have completed. See commands
        MEASure:FREQuency and MEASure:TIMe for details on the format of
        results returned. When the sample size is greater than one,
        results are separated from each other by commas ( , ).
        Manual p.99
        """
        try:
            return self.query("FETC{0}?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Fetch() : '+str(err))
            return np.nan

    def Abort(self, front = True):
        """
        Stop any measurement in progress and discard any results
        produced.
        Manual p.99
        """
        try:
            self.write("ABOR{0}".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Abort() : '+str(err))
            return np.nan

    def Stop(self, front = True):
        """
        Stop any measurement in progress, but do not discard any
        results produced.
        Manual p.99
        """
        try:
            self.write("STOP{0}".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Stop() : '+str(err))
            return np.nan

    #################################################################
    ##########  Calculate Subsystem                        ##########
    #################################################################
    """
    Commands in the Calculate Subsystem can apply to either the front
    or rear input. The user selects the input by optionally appending
    a 1 or 2 to the CALCulate keyword. When the suffix is 1 or
    omitted, the front input is selected. When the suffix is 2, the
    rear input is selected.
    """

    def CalculateFilter(self, filtersetting):
        """
        The first definition changes input filter for frequency
        measurements. The second definition queries the current input
        filter. There are two filter options: NONE and FAST. If NONE
        is selected, then just two time tags are used to generate a
        frequency measurement, one at the beginning of the gate
        interval and one at the end. When the FAST filter is
        selected, up to 625 time tags are averaged together at the
        beginning of the gate interval to produce an average starting
        time tag. Another 625 time tags are averaged together at the
        end of the gate interval to produce an average ending time tag.
        These two averaged time tags are used to compute a frequency
        measurement. The benefit of this filter is that it is effective
        in removing broadband noise inherent in the measurement. Noise
        can be reduced by more than a factor of 10 with the use of
        this filter. The default filter is FAST and it is the
        recommended setting for most measurements.
        Manual p.100
        """
        if filtersetting not in ['FAST', 'NONE']:
            logging.warning("FS740 warning in CalculateFilter() : filtersetting\
                             invalid value")
            return
        try:
            self.write("CALC:FILT {0}".format(filtersetting))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in CalculateFilter() : '+str(err))
            return np.nan

    def ReadCalculateFilter(self):
        return self.query("CALC:FILT?")

    def SetCalculateReference(self, freq = 'DEF', front = True):
        """
        For each frequency measurement, the reference frequency is
        subtracted from the measured frequency to produce the final
        result. This enables one to monitor the deviation of the
        frequency from a specified target value rather than the
        absolute frequency itself. The first definition sets the
        reference frequency to <frequency>. If <frequency> is omitted,
        it is set to the value of the most recent measurement. The
        second definition queries the current reference frequency. The
        default reference frequency is 0 Hz.
        Manual p.100
        """
        if not self.ValidateFrequency(freq):
            logging.warning("FS740 warning in SetCalculateReference() : \
                             freq invalid")
            return
        try:
            self.write("CALC{0}:REF {1}".format(1 if front else 2, freq))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SetCalculateReference() : '\
                            +str(err))

    def QueryCalculateReference(self, front = True):
        try:
            return self.query("CALC{0}:REF?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryCalculateReference() : '\
                	        +str(err))
            return np.nan


    def CalculateStability(self, front = True):
        """
        This command computes the frequency stability, or Allan
        deviation, of all frequency measurements for time intervals
        from 10 ms to 50 million seconds in a 1, 2, 5 sequence and
        returns them as a comma delimited list of relative Allan
        deviations.
        Manual p.101

        Returns 10 ms, 20 ms, 50 ms, 100 ms, ... , 5e7 s.
        """
        try:
            return self.query("CALC{0}:STAB?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in CalculateStability() : '+str(err))
            return np.nan

    def CalculateStatistics(self, front = True):
        """
        This command computes some basic statistics of the current
        measurement and returns the following values in a comma
        separated list: the mean, the Allan deviation, the minimum,
        the maximum, and the number of measurements made.
        Manual p.101

        Returns mean, ASD, min, max and # measurements.
        """
        try:
            return self.query("CALC{0}:STAT?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in CalculateStatistics() : '+str(err))
            return np.nan

    #################################################################
    ##########  Data Subsystem                             ##########
    #################################################################

    def DataCount(self, front = True):
        """
        This command returns the total number of measurements
        completed so far.
        Manual p.102
        """
        try:
            return int(self.query("DATA{0}:COUN?".format(
                1 if front else 2)))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning inDataCount() : '+str(err))
            return np.nan

    def DataPoints(self, front = True):
        """
        This command returns the total number of measurements stored
        in internal memory.
        Manual p.102
        """
        try:
            return int(self.query("DATA{0}:POIN?".format(1 if front else 2)))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in DataPoints() : '+str(err))
            return np.nan

    def DataRead(self, index, count, front = True):
        """
        This command returns <count> measurements stored in internal
        memory, starting with the one located at <index>.
        Manual p.103
        """
        if not isinstance(index, int):
            logging.warning("FS740 warning in DataRead() : index invalid type")
            return np.nan
        if not isinstance(count, int):
            logging.warning("FS740 warning in DataRead() : count invalid type")
            return np.nan
        if index < 0:
            logging.warning("FS740 warning in DataRead() : index out of range")
            return np.nan
        if count < 0:
            logging.warning("FS740 warning in DataRead() : count out of range")
            return np.nan
        try:
            return self.query("DATA{0}:READ? {1}, {2}".format(
                1 if front else 2, index, count))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in DataRead() : '+str(err))
            return np.nan

    def DataRemove(self, count, front = True):
        """
        This command returns the first <count> measurements stored in
        internal memory and removes them from memory.
        Manual p.103
        """
        if not isinstance(count, int):
            logging.warning("FS740 warning in DataRemove() : count invalid type")
            return np.nan
        if count < 0:
            logging.warning("FS740 warning in DataRemove() : count out of range")
            return np.nan
        try:
            return self.query("DATA{0}:REM? {1}".format(
                1 if front else 2, count))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in DataRemove() : '+str(err))
            return np.nan
    #################################################################
    ##########  GPS Subsystem                              ##########
    #################################################################
    """
    Not implemented:
        GPS:CONFig:SAVe
        GPS:CONFig:SURVey:Mode
        GPS:CONFig:SURVey:FIXes
        GPS:POSition:SURVey:DELete
        GPS:POSition:SURVey:PROGress
        GPS:POSition:SURVey:SAVe
        GPS:POSition:SURVey:STARt
        GPS:POSition:SURVey:STATe
        GPS:UTC:OFFSet
    """
    def GPSConfigAlignment(self, alignment):
        """
            GPS:CONFig[:TIMing]:ALIGnment [{GPS|UTC}]
            GPS:CONFig[:TIMing]:ALIGnment?
        The first definition sets the GPS 1pps alignment. If alignment is
        omitted, the default alignment is UTC. The second definition queries the
        current GPS 1pps alignment. When GPS is selected, all timing is aligned
        to GPS. When UTC is selected, all timing is aligned to UTC. The user
        must execute the command GPS:CONF:SAVE to save the current value to
        nonvolatile memory.
        Manual p.105
        """
        try:
            self.write("GPS:CONF:ALIG "+alignment)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSConfigAlignment() : '+str(err))
            return np.nan

    def QueryGPSConfigAlignment(self):
        try:
            return self.query("GPS:CONF:ALIG?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryGPSConfigAlignment() : '\
                            +str(err))
            return np.nan

    def GPSConfigMode(self, mode):
        """
            GPS:CONFig:MODe <anti-jamming>, <elevation mask>, <signal mask>
            GPS:CONFig:MODe?
        The first definition enables the user to set anti-jamming mode, the
        elevation mask and the signal mask. The second definition queries the
        current values for these parameters. <Anti-jamming> is a Boolean value
        which enables or disables anti-jamming in the receiver. The factory
        default is enabled. <Elevation mask> is the elevation angle in radians,
        below which satellites are ignored in over determined clock mode.
        It can range from 0 to π/2. <Signal mask> is the minimum signal level in
        dbHz, below which satellites are ignored in over determined clock mode.
        It can range from 0 to 55 dBHz. The default value for both masks is 0.
        The user must execute the command GPS:CONF:SAVE to save the current
        values to nonvolatile memoryself.
        """
        try:
            self.write("GPS:CONF:MOD "+mode)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSConfigMode() : '+str(err))

    def QueryGPSConfigMode(self):
        """
        Query the GPS Config Mode.
        Returns anti-jamming, elevation mask and signal mask:
         - anti-jamming is a Boolean value
         - elevation mask is the elevation angle in radians below which satellites
           are ignored in over determined clock mode
         - signal mask is the minimum signal level in dbHz below which satellites
           are ignored in over determined clock mode
        """
        try:
            return self.query("GPS:CONF:MOD?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryGPSConfigMode() : '+str(err))
            return np.nan

    def GPSConfigQuality(self, option = '3SAT'):
        """
            GPS:CONFig[:TIMing]:QUALity [{1SAT|3SAT}]
            GPS:CONFig[:TIMing]:QUALity?
        The first definition sets the minimum number of satellites the receiver
        must track before outputting a hardware 1pps pulse. If omitted, the
        default quality is 3 satellites. The second definition queries the
        current timing quality. Timing quality generally increases as the number
        of satellites increases. However, the user must also consider
        reliability and holdover performance. Degraded performance may be
        preferred over no timing whatsoever. The user must execute the command
        GPS:CONF:SAVE to save the current value to nonvolatile memory.
        """
        try:
            self.write("GPS:CONF:QUAL "+option)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSConfigQuality() : '+str(err))

    def QueryGPSConfigQuality(self):
        try:
            return self.query("GPS:CONF:QUAL?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryGPSConfigQuality() : '\
                             +str(err))
            return np.nan

    def GPSConfigADelay(self, delay):
        """
            GPS:CONFig[:TIMing]:ADELay <delay>
            GPS:CONFig[:TIMing]:ADELay?
        The first definition sets the antenna delay to <delay> in seconds. The
        second definition queries the current antenna delay in seconds. The
        <delay> may range from −0.1 s to +0.1 s. Note that the user should
        enter a negative number here to compensate for the length of their
        antenna cable. It affects the timing of all inputs and outputs. The
        user must execute the command GPS:CONF:SAVE to save the current value
        to nonvolatile memory.
        """
        try:
            self.write("GPS:CONF:ADEL "+delay)
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSConfigADelay() : '+str(err))

    def QueryGPSConfigADelay(self):
        return self.query("GPS:CONF:ADEL?")

    def GPSPosition(self):
        """
        Query the GPS position.
        Returns latitude, longitude and altitude.
        Latitude is specified in radians, with positive values
        indicating north, and negative values indicating south.
        Longitude is specified in radians, with positive values
        indicating east, and negative values indicating west.
        Altitude is specified in meters above average sea levels.
        Manual p.106
        """
        try:
            return self.query("GPS:POS?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSPosition() : '+str(err))
            return np.nan

    def GPSPositionHoldState(self):
        """
        Query whether the GPS receiver is in position hold mode where
        all satellites are being used for maximum timing performance.
        0: min performance
        1: hold mode, max performance
        Manual p.107
        """
        try:
            return self.query("GPS:POS:HOLD:STAT?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSPositionHoldState() : '\
                             +str(err))
            return np.nan

    def GPSSatelliteTracking(self):
        """
        Query which GPS satellites are being tracked by the receiver.
        The query returns the number of satellites being tracked,
        followed by the IDs of the satellites as a comma ( , )
        separated list.
        Manual p.108
        """
        try:
            return self.query("GPS:SAT:TRAC?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSSatelliteTracking() : '+str(err))
            return np.nan

    def GPSSatelliteTrackingStatus(self):
        """
        The receiver has 20 channels for tracking satellites. This
        command returns the information shown below for each
        channel, successively.
        index: parameter
        0: Satellite ID number
        1: Acquired
        2: Ephemeris
        3: Is old
        4: Signal level in dbHz
        5: Elevation in degrees
        6: Azimuth in degrees
        7: Space vehicle type
        Manual p.109
        """
        try:
            return self.query("GPS:SAT:TRAC:STAT?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in GPSSatelliteTrackingStatus() : '+str(err))
            return np.nan

    #################################################################
    ##########  Input Subsystem                            ##########
    #################################################################

    @staticmethod
    def ValidateMinDefMax(value):
        return value in ['MIN', 'MAX', 'DEF']

    @staticmethod
    def ValidateLevel(level):
        if self.ValidateMinDefMax(level):
            return True
        if not isinstance(level, (int, float)):
            logging.warning("FS740 warning in ValidateLevel() : level invalid type")
            return False
        if  not ((level >= -3.0) and (level <= 3.0)):
            logging.warning("FS740 warning in ValidateLevel() : level out of range")
            return False
        return True

    def InputLevel(self, level, front = True):
        """
        Set input trigger level.
        Manual p.110
        """
        if not self.ValidateLevel(level):
            logging.warning("FS740 warning in InputLevel() : level invalid")
            return
        try:
            self.write("INP{0}:LEV {1}".format(1 if front else 2, level))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in InputLevel() : '+str(err))

    def QueryInputLevel(self, front = True):
        """
        Read input trigger level.
        Manual p.110
        """
        try:
            return self.query("INP{0}:LEV?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryInputTypeParameters() : '\
                            +str(err))
            return np.nan

    def InputSlope(self, slope, front = True):
        """
        Set input slope.
        Manual p.110
        """
        if not slope in ['NEG', 'POS', 'DEF']:
            logging.warning("FS740 warning in InputSlope() : slope invalid")
            return
        try:
            self.write("INP{0}:SLOP {1}".format(1 if front else 2, slope))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in InputSlope() : '+str(err))

    def QueryInputSlope(self, front = True):
        """
        Read input slope.
        Manual p.110
        """
        try:
            return self.query("INP{0}:SLOP?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QueryInputSlope() : '+str(err))
            return np.nan

    #################################################################
    ##########  Route Subsystem                            ##########
    #################################################################
    """
    Not implemented:
        ROUTe:OPTion

    Option not installed in CeNTREX FS740
    """

    #################################################################
    ##########  Sample Subsystem                           ##########
    #################################################################

    @staticmethod
    def ValidateCount(count):
        if count in ['DEF', 'MIN', 'MAX']:
            return True
        if not isinstance(count, int):
            logging.warning("FS740 warning in ValidateCount() : count invalid type")
            return False
        if not ((count >= 1) and (count <= int(1e9))):
            logging.warning("FS740 warning in ValidateCount() : count out of range")
        return True

    def SampleCount(self, count, front=True):
        """
        Set sample count.
        Manual p.111
        """
        if not self.ValidateCount(count):
            logging.warning("FS740 warning in SampleCount() : count invalid")
        try:
            self.write("SAMP{0}:COUN {1}".format(1 if front else 2, count))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SampleCount() : '+str(err))

    def QuerySampleCount(self, front=True):
        try:
            return self.query("SAMP{0}:COUN?".format(1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySampleCount() : '+str(err))
            return np.nan

    #################################################################
    ##########  Sense Subsystem                            ##########
    #################################################################

    @staticmethod
    def ValidateGate(gate):
        if gate in ['DEF', 'MIN', 'MAX']:
            return True
        if not isinstance(gate, (int, float)):
            logging.warning("FS740 warning in ValidateGate() : gate invalid type")
            return False
        if not ((gate >= 1e-2) and (gate <= 1e3)):
            logging.warning("FS740 warning in ValidateGate() : gate out of range")
            return False
        return True

    def SenseFrequencyGate(self, gate, front = True):
        """
        Set gate for frequency measurement.
        Manual p.111
        """
        if not self.ValidateGate(gate):
            logging.warning("FS740 warning in SenseFrequencyGate() : \
                             gate invalid")
        try:
            self.write("SENS{0}:FREQ:GATE {1}".format(1 if front else 2,
                                                    gate))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SenseFrequencyGate() : '+str(err))
            return np.nan

    def QuerySenseFrequencyGate(self, front = True):
        try:
            return self.query('SENS{0}:FREQ:GATE?'.format(
                1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning inQuerySenseFrequencyGate() : '+str(err))
            return np.nan

    @staticmethod
    def ValidateTimeout(timeout):
        if self.ValidateMinDefMax(timeout):
            return True
        if not isinstance(timeout, (int, float)):
            logging.warning("FS740 warning in ValidateTimeout() : timeout \
                             invalid type")
            return False
        if not ((timeout >= 1e-2) & (timeout <= 2e3)):
            logging.warning("FS740 warning in ValidateTimeout() : timeout out\
                             of range")
            return False
        return True


    def SenseFrequencyTimeout(self, timeout, front = True):
        """
        Sets time out period for frequency measurements to <timeout>
        in seconds.
        Manual p.112
        """
        if not self.ValidateTimeout(timeout):
            logging.warning("FS750 warning in SenseFrequencyTimeout() : \
                             timout invalid")
            return
        try:
            self.write("SENS{0}:FREQ:TIM {1}".format(1 if front else 2,
                                                   timeout))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySenseFrequencyGate() : '+str(err))

    def QuerySenseFrequencyTimeout(self, front = True):
        try:
            return self.query("SENS{0}:FREQ:TIM?".format(
                1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySenseFrequencyTimeout() : ' \
                            +str(err))
            return np.nan

    def SenseTimeBMode(self, mode, front = True):
        """
        Sets buffer mode for time measurements.
        If KFIRst (Keep First) is specified then older measurements
        are preserved and new measurements are dropped. If KLASt
        (Keep Last) is specified then older measurements are dropped
        and newer measurements are preserved. The default value is
        KLASt.
        Manual p.112
        """
        if  mode not in ['KFIR', 'KLAS']:
            logging.warning("FS740 warning in SenseTimeBMode() : mode invalid")
        try:
            self.write("SENS{0}:TIM:BMOD {1}".format(1 if front else 2,
                                                  mode))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SenseTimeBMode() : '+str(err))

    def QuerySenseTimeBMode(self, front = True):
        try:
            return self.query("SENS{0}:TIM:BMOD?".format(
                1 if front else 2))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySenseTimeBMode() : ' \
                            +str(err))
            return np.nan

    #################################################################
    ##########  Source Subsystem                           ##########
    #################################################################

    """
    Not implemented:
        SOURce:PHASe
        SOURce:PHASe:REFerence
        SOURce:PHASe:SYNChronize
        SOURce:PHASe:SYNChronize:AUTo
        SOURce:PHASe:SYNChronize:TDELay
        SOURce3:PULSe:DCYCle
        SOURce3:PULSe:PERiod
        SOURce3:PULSe:VIEW
        SOURce3:PULSe:WIDTh
    """
    def SetFrequencyPulse(self, freq):
        """
        Wrapper function to change the frequency of the pulse output
        """
        freq = float(freq)
        self.Source3Function('PULS')
        self.SourceFrequency(freq, 3)
        if not freq == float(self.QuerySourceFrequency(3)):
            logging.warning("FS740 warning in SetFrequency() : \
                             Pulse frequency not set")
            return



    @staticmethod
    def ValidateSourceOutput(output):
        if not output in [1,2,3]:
            logging.warning("FS740 warning in ValidateSourceOutput() : \
                             output invalid")
            return False
        return True

    def ValidateSourceFrequency(self, freq, output):
        if self.ValidateMinDefMax(freq):
            return True
        if not isinstance(freq, (int, float)):
            logging.warning("FS740 warning in ValidateSourceFrequency() : " +
                                 "freq invalid type")
            return False
        if output == 1:
            if not ((freq >= 1e-3) and (freq <= 30.1e6)):
                logging.warning("FS740 warning in ValidateSourceFrequency() : " +
                                 "freq out of range")
                return False
            else:
                return True

        elif output == 2:
            if not ((freq >= 1e-3) and (freq <= 1e6)):
                logging.warning("FS740 warning in ValidateSourceFrequency() : " +
                                 "freq out of range")
                return False
            else:
                return True
        elif output == 3:
            if not ((freq >= 1e-3) and (freq <= 25e6)):
                logging.warning("FS740 warning in ValidateSourceFrequency() : " +
                                 "freq out of range")
                return False
            else:
                return True
        return True

    def SourceFrequency(self, freq, output):
        """
        Sets the output frequency for the selected output to <freq>
        in Hz.
        Manual p.113
        """
        if not self.ValidateSourceOutput(output):
            logging.warning("FS740 warning in SourceFrequency() : \
                             output invalid")
            return
        if not self.ValidateSourceFrequency(freq, output):
            logging.warning("FS740 warning in SourceFrequency() : \
                             freq invalid")
            return
        try:
            self.write("SOUR{0}:FREQ {1}".format(output, freq))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SourceFrequency() : ' \
                            +str(err))

    def QuerySourceFrequency(self, output):
        if not self.ValidateSourceOutput(output):
            logging.warning("FS740 warning in QuerySourceFrequency() : \
                             output invalid")
            return np.nan
        try:
            return self.query("SOUR{0}:FREQ?".format(output))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySourceFrequency() : ' \
                            +str(err))
            return np.nan

    def Source2Function(self, shape):
        """
        Sets the function for the Aux output.
        Manual p.114
        """
        if not shape in ['SIN', 'TRI', 'SQU', 'HMHZ' 'IRIG']:
            logging.warning("FS740 warning in Source2Function() : \
                             shape invalid")
            return
        try:
            self.write("SOUR2:FUNC {0}".format(shape))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Source2Function() : ' \
                            +str(err))

    def QuerySource2Function(self):
        try:
            return self.query("SOUR2:FUNC?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySource2Function() : ' \
                            +str(err))
            return np.nan

    def Source3Function(self, shape):
        """
        Sets the function for the Pulse output.
        Manual p.114
        """
        if not shape in ['PULS', 'IRIG']:
            logging.warning("FS740 warning in Source3Function() : \
                             shape invalid")
            return
        try:
            self.write("SOUR3:FUNC {0}".format(shape))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in Source3Function() : ' \
                            +str(err))

    def QuerySource3Function(self):
        try:
            return self.query("SOUR3:FUNC?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySource3Function() : ' \
                            +str(err))
            return np.nan

    def SourceVoltage(self, voltage, output):
        """
        Sets the AC voltage level for the output to <voltage> or the
        selected limit.
        Manual p.118
        """
        if not self.ValidateOutput(output):
            logging.warning("FS740 warning in SourceVoltage() : \
                             output invalid")
            return
        try:
            self.write("SOUR{0}:VOLT {1}".format(output, voltage))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SourceVoltage() : ' \
                            +str(err))

    def QuerySourceVoltage(self, output):
        if not self.ValidateSourceOutput(output):
            logging.warning("FS740 warning in QuerySourceVoltage() : \
                             output invalid")
            return np.nan
        try:
            return self.query("SOUR{0}:VOLT?".format(output))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySourceVoltage() : ' \
                            +str(err))
            return np.nan

    def SourceVoltageUnits(self, output, unit):
        """
        Selects the default units when specifying or querying AC
        voltage levels with the command SOUR:VOLT.
        Manual p.118
        """
        if not self.ValidateSourceOutput(output):
            logging.warning("FS740 warning in SourceVoltageUnits() : \
                             output invalid")
            return
        if not output in [1,2]:
            logging.warning("FS740 warning in SourceVoltageUnits() : \
                             output invalid")
            return
        if not unit in ['VPP', 'VRMS', "DBM"]:
            logging.warning("FS740 warning in SourceVoltageUnits() : \
                             unit invalid")
        try:
            self.write("SOUR{0}:VOLT:UNIT {1}".format(output, unit))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SourceVoltageUnits() : ' \
                            +str(err))

    def QuerySourceVoltageUnits(self, output):
        if not self.ValidateSourceOutput(output):
            logging.warning("FS740 warning in QuerySourceVoltageUnits() : \
                             output invalid")
        try:
            return self.query("SOUR{0}:VOLT:UNIT?".format(output))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySourceVoltageUnits() : ' \
                            +str(err))
            return np.nan

    #################################################################
    ##########  Status Subsystem                           ##########
    #################################################################

    """
    Not implemented:
        STATus:GPS:ENABle
        STATus:OPERation:ENABle
        STATus:QUEStionable:ENABle
    """

    def StatusGPSCondition(self):
        """
        Query the current condition of the GPS receiver.
        Manual p.119
        bit : name
        0 :  Time not set
        1 :  Antenna open
        2 :  Antenna short
        3 :  No satellites
        4 :  UTC unknown
        5 :  Survey in progress
        6 :  No position stored
        7 :  Leap second pending
        8 :
        9 :  Position questionable
        10:
        11:  Almanac incomplete
        12:  No timing pulses
        13:
        14:
        15:
        Manual p.119
        """
        try:
            return self.query("STAT:GPS:COND?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in StatusGPSCondition() : ' \
                            +str(err))
            return np.nan

    def StatusGPSEvent(self):
        """
        Query the GPS receiver status event register. Returns all
        bits that have been set since the previous query. The query
        then clears all bits.
        Manual p.120
        """
        try:
            return self.query("STAT:GPS:EVEN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in StatusGPSEvent() : ' \
                            +str(err))
            return np.nan

    def StatusOperationCondition(self):
        """
        Query the current condition of operational status for the
        FS740.
        Manual p.120

        bit : name           : meaning
        0   :                :
        1   : setting        : Hardware instrument settings are
                               changing.
        2   :                :
        3   :                :
        4   : measure front  : Measurement on front input in progress.
        5   : measure rear   : Measurement on rear input in progress.
        6   : event front    : Timing event detected on front input.
        7   : event rear     : Timing event detected on rear input.

        """
        try:
            return self.query("STAT:OPER:COND?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in StatusOperationCondition() : ' \
                            +str(err))
            return np.nan

    def StatusOperationEvent(self):
        """
        Query the event register for operational status. This returns
        all bits that have been set since the previous query. The
        query then clears all bits.
        Manual p.120
        """
        try:
            return self.query("STAT:OPER:EVEN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in StatusOperationEvent() : ' \
                            +str(err))
            return np.nan

    def StatusQuestionableCondition(self):
        """
        Query the current condition of questionable status for the
        FS740.
        Manual p.121

        bit : name           : meaning
        0   : time of day    : Instrument time of day has not been
                               set by GPS receiver. Absolute time
                               measurements are invalid.
        1   : warm up        : The timebase is still warming up.
                               Frequency drift will be much larger
                               than normal.
        2   : time unluck    : The timebase is not locked to gps.
                               Time and frequency measurements may be
                               degraded.
        3   :
        4   :
        5   : freq stability : The timebase has not been locked to
                               GPS long enough to reach optimum freq
                               stability.
        6   :
        7   :
        8   :
        9   :
        10  : Rb unlock      : The installed Rb timebase is unlocked.
                               Its frequency is not stable.
        11  : PLL unlock     : One of the internal PLL circuits in
                               in the FS740 has become unlocked. This
                               may signal a need for instrument
                               repair.
        12  : EFC 10MHz      : Indicates that the frequency control
                               of the internal TCXO is near the rail.
        13  : EFC GPS        : Indicates that the frequency control
                               for the installed timebase is
                               saturated. This might indicate a large
                               timing error.
        """
        try:
            return self.query("STAT:QUES:COND?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in StatusQuestionableCondition() : ' \
                            +str(err))
            return np.nan

    def StatusQuestionableEvent(self):
        """
        Query the event register for questionable status. This
        returns all bits that have been set since the previous query.
        The query then clears all bits.
        Manual p.121
        """
        try:
            return self.query("STAT:QUES:EVEN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in StatusQuestionableEvent() : ' \
                            +str(err))
            return np.nan

    #################################################################
    ##########  System Subsystem                           ##########
    #################################################################

    """
    Not implemented:
        SYSTem:ALARm:FORCe:STATe
        SYSTem:TIMe:LOFFset
    """

    def SystemAlarm(self):
        """
        Query the current state of the system alarm. The FS740 will
        return 1 if the alarm is asserted, otherwise 0.
        Manual p.122
        """
        try:
            return self.query("SYST:ALAR?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarm() : ' \
                            +str(err))
            return np.nan

    def SystemAlarmClear(self):
        """
        Clear the event register for the system alarm.
        Manual p.122
        """
        try:
            self.write("SYST:ALAR:CLE")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmClear() : ' \
                            +str(err))

    def SystemAlarmCondition(self):
        """
        Query the condition register for the system alarm.
        Manual p.122
        """
        try:
            return self.query("SYST:ALAR:COND?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmCondition() : ' \
                            +str(err))
            return np.nan

    def SystemAlarmEnable(self, mask):
        """
        Mask possible alarm conditions so that only those that are
        enabled here can cause the system alarm to be asserted.
        When the current mode for command SYST:ALARm:MODe is TRACk,
        this register masks the condition register for the system alarm,
        SYST:ALARm:CONDition. When the current mode for command
        SYST:ALARm:MODe is LATCh, this register masks the event
        register for the system alarm, SYST:ALARm:EVENt
        Manual p.123
        """
        try:
            self.write("SYST:ALAR:ENAB {0}".format(mask))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmEnable() : ' \
                            +str(err))

    def QuerySystemAlarmEnable(self):
        try:
            return self.query("SYST:ALAR:ENAB")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemAlarmEnable() : ' \
                            +str(err))
            return np.nan

    def SystemAlarmEvent(self):
        """
        Query the event register for the system alarm. This
        register indicates which of the possible alarm conditions
        that have been latched since the last time the event
        register was cleared. When the current mode for command
        SYST:ALARm:MODe is LATCh the system alarm will be asserted
        if an event condition is true AND it is enabled in the
        enable register. Note that unlike the event registers in
        the Status Subsystem, reading this register does not clear
        it. It must be explicitly cleared with the
        SYSTem:ALARm:CLEar command.
        Manual p.123
        """
        try:
            return self.query("SYS:ALAR:EVEN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmEvent() : ' \
                            +str(err))
            return np.nan

    def SystemAlarmMode(self, mode):
        """
        Sets the alarm mode to one of three options: track, latch,
        or force.
        Tracking mode causes the alarm to follow current conditions.
        The alarm is asserted when current limits are exceeded. The
        alarm is de-asserted when current limits are no longer
        exceeded.
        Latching mode causes the alarm to be asserted when current
        limits are exceeded. However, the alarm will not be
        de-asserted until explicitly requested to do so and the
        limit is no longer exceeded.
        In force mode, the user manually sets the state of the alarm.
        Manual p.124
        """
        if not mode in ['TRAC', 'LATC', 'FORC']:
            logging.warning("FS740 warning in SystemAlarmMode() : \
                             mode invalid")
        try:
            self.write("SYST:ALAR:MOD {0}".format(mode))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmMode() : ' \
                            +str(err))

    def QuerySystemAlarmMode(self):
        try:
            return self.query("SYST:ALAR:MOD?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemAlarmMode() : ' \
                            +str(err))
            return np.nan

    @staticmethod
    def ValidateInterval(interval):
        if self.ValidateMinDefMax(interval):
            return True
        else:
            if not ((type(interval) == int) or (type(interval) == float)):
                logging.warning("FS740 warning in ValidateInterval() : \
                                 interval invalid type")
                return False
            if not ((interval > 5e-8) and (interval <= 1)):
                logging.warning("FS740 warning in ValidateInterval() : \
                                 interval out of range")
                return False
        return True

    def SystemAlarmGPSTInterval(self, interval):
        """
        Sets the time interval between GPS and the internal timebase
        that must be exceeded before the alarm condition for a timing
        error is asserted. The <time error> may range from 50 ns to 1
        s. The default is 100 ns.
        Manual p.124
        """
        if not self.ValidateInterval(interval):
            logging.warning("FS740 warning in SystemAlarmGPSTInterval() : \
                             interval invalid")
        try:
            self.write("SYST:ALAR:TINT {0}".format(interval))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmGPSTInterval() : ' \
                            +str(err))

    def QuerySystemAlarmGPSTInterval(self):
        try:
            return self.query("SYST:ALAR:TINT")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemAlarmGPSTInterval() : ' \
                            +str(err))
            return np.nan

    @staticmethod
    def ValidateDuration(duration):
        if not self.ValidateMinDefMax(duration):
            logging.warning("FS740 warning in ValidateDuration() : \
                             duration invalid")
            return False
        elif not isinstance(duration, (float, int)):
            logging.warning("FS740 warning in ValidateDuration() : \
                             duration invalid type")
            return False
        elif not duration > 0:
            logging.warning("FS740 warning in ValidateDuration() : \
                             duration out of range")
            return False
        else:
            return True

    def SystemAlarmHoldoverDuration(self, duration):
        """
        Sets the amount of time in seconds that the FS740 must be
        in holdover before the alarm condition for holdover is
        asserted. The <duration> may be any 32 bit unsigned integer.
        The default is 0.
        Manual p.124
        """
        if not self.ValidateDuration(duration):
            logging.warning("FS740 warning in SystemAlarmHoldoverDuration() : \
                             duration invalid")
            return
        try:
            self.write("SYST:ALAR:HOLD:DUR {0}")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemAlarmHoldoverDuration() : ' \
                            +str(err))

    def QuerySystemAlarmHoldoverDuration(self):
        try:
            self.query("SYST:ALAR:HOLD:DUR?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemAlarmHoldoverDuration() : ' \
                            +str(err))
            return np.nan

    def SystemCommunicateLan(self):
        """
        Query whether the FS740 is connected to the Ethernet LAN.
        The query returns 1 if connected, otherwise 0.
        Manual p.125
        """
        try:
            return self.query("SYST:COMM:LAN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLan() : ' \
                            +str(err))

    def SystemCommunicateLanSpeed(self, speed = '100BASTET'):
        """
        Configures the speed of the Ethernet network to which the
        FS740 is connected, 10BaseT or 100BaseT. If omitted the
        command defaults to 100BaseT. Note that changes to this
        configuration do not take effect until the LAN is reset
        via a SYSTem:COMMunicate:LAN:RESet command or the power
        is cycled.
        Manual p.125
        """
        if not speed in ['10BASET', '100BASET']:
            logging.warning("FS740 warning in SystemCommunicateLanSpeed() : \
                             speed invalid")
            return
        try:
            self.write("SYST:COMM:LAN:SPE {0}".format(speed))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLan() : ' \
                            +str(err))

    def QuerySystemCommunicateLanSpeed(self):
        """
        Manual p.125
        """
        try:
            return self.query("SYST:COMM:LAN:SPE?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemCommunicateLanSpeed() : ' \
                            +str(err))
            return np.nan

    def SystemCommunicateLanDHCP(self, DHCP = True):
        """
        Enables or disables DHCP for configuring the TCP/IP address
        of the FS740. Note that the new configuration does not take
        effect until the LAN is reset via a
        SYSTem:COMMunicate:LAN:RESet command or the power is cycled.
        Manual p.125
        """
        try:
            self.write("SYST:COMM:LAN:DHCP {0}".format(
                'ON' if DHCP else 'OFF'))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLanDHCP() : ' \
                            +str(err))

    def QuerySystemCommunicateLanDHCP(self):
        try:
            return self.query("SYST:COMM:LAN:DHCP?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemCommunicateLanDHCP() : ' \
                            +str(err))

    def SystemCommunicateLanGateway(self, gateway):
        """
        Sets the IP address of the gateway or router on the users
        TCP/IP network to be used in static configurations.
        The <ip address> should be specified as a string in the form
        “xxx.xxx.xxx.xxx” where each xxx is replaced by an integer in
        the range from 0 to 255.
        Manual p.126
        """
        try:
            self.write("SYST:COMM:LAN:GAT {0}".format(gateway))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLanGateway() : ' \
                            +str(err))
            return np.nan

    def QuerySystemCommunicateLanGateway(self, option = 'CURR'):
        """
        Accepts 'CURR'ent and 'STAT'ic options.
        Manual p.126
        """

        if not option in ['CURR', 'STAT']:
            logging.warning("FS740 warning in QuerySystemCommunicateLanGateway() : \
                             option invalid")
            return np.nan
        try:
            return self.query("SYST:COMM:LAN:GAT? {0}")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemCommunicateLanGateway() : ' \
                            +str(err))
            return np.nan

    def SystemCommunicateLanIPAddress(self, ip):
        """
        Sets the IP address of the FS740 on the users TCP/IP network
        to be used in static configurations.
        The <ip address> should be specified as a string in the form
        “xxx.xxx.xxx.xxx” where each xxx is replaced by an integer in
        the range from 0 to 255.
        Manual p.126
        """
        try:
            self.write("SYST:COMM:LAN:IPAD {0}".format(ip))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLanIPAddress() : ' \
                            +str(err))

    def QuerySystemCommunicateLanIPAddress(self, option = 'CURR'):
        """
        Accepts 'CURR'ent and 'STAT'ic options.
        Manual p.126
        """
        if not option in ['CURR', 'STAT']:
            logging.warning("FS740 warning in QuerySystemCommunicateLanIPAddress() : \
                             option invalid")
            return np.nan
        try:
            return self.query("SYST:COMM:LAN:IPAD? {0}")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemCommunicateLanIPAddress() : ' \
                            +str(err))
            return np.nan

    def SystemCommunicateLanSMask(self, smask):
        """
        Sets the subnet mask for the users TCP/IP network to be used
        in static configurations.
        The <ip address> should be specified as a string in the form
        “xxx.xxx.xxx.xxx” where each xxx is replaced by an integer in
        the range from 0 to 255.
        Manual p.127
        """
        try:
            self.write("SYST:COMM:LAN:SMAS {0}".format(smask))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLanSMask() : ' \
                            +str(err))

    def QuerySystemCommunicateLanSMask(self, option = 'CURR'):
        """
        Accepts 'CURR'ent and 'STAT'ic options.
        Manual p.127
        """
        if not option in ['CURR', 'STAT']:
            logging.warning("FS740 warning in QuerySystemCommunicateLanSMask")
            return np.nan
        try:
            return self.query("SYST:COMM:LAN:SMAS? {0}")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemCommunicateLanSMask() : ' \
                            +str(err))

    def SystemCommunicateLanReset(self):
        """
        """
        try:
            self.write("SYST:COMM:LAN:RESET")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLanReset() : ' \
                            +str(err))

    def SystemCommunicateSerialBAUD(self, baud):
        """
        Configures the RS-232 port to operate at the selected baud
        rate. Note that the new configuration does not take effect
        until the port is reset via a SYSTem:COMMunicate:SERial:RESet
        command or the power is cycled.
        Manual p.127
        """
        if not baud in [4800, 9600, 19200, 38400, 157600, 115200]:
            logging.warning("FS740 warning in SystemCommunicateSerialBAUD() : \
                             baud rate invalid")
        try:
            self.write("SYST:COMM:SER:BAUD {0}".format(baud))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateSerialBAUD() : ' \
                            +str(err))

    def QuerySystemCommunicateSerialBaud(self):
        try:
            self.query("SYST:COMM:SER:BAUD?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemCommunicateSerialBaud() : ' \
                            +str(err))
            return np.nan

    def SystemCommunicateSerialReset(self):
        """
        Reset the serial port and activate it using the current
        configured baud rate.
        Manual p.128
        """
        try:
            self.write("SYST:COMM:SER:BAUD:RESET")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateSerialReset() : ' \
                            +str(err))

    def SystemCommunicateLock(self):
        """
        Request an exclusive lock on communication with the FS740.
        The FS740 will return 1 if the request is granted, otherwise
        0. When an interface has an exclusive lock on communication
        with the FS740, other remote interfaces as well as the front
        panel are prevented from changing the instrument state. The
        user should call the command SYSTem:COMMunicate:UNLock command
        to release the exclusive lock when it is no longer needed.
        Manual p.128
        """
        try:
            return self.query("SYST:COMM:LOCK?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateLock() : ' \
                            +str(err))

    def SystemCommunicateUnlock(self):
        """
        Release an exclusive lock on communication with the FS740 that
        was previously granted with the SYSTem:COMMunicate:LOCK command.
        The FS740 will return 1 if the lock was released, otherwise 0.
        Manual p.128
        """
        try:
            return self.query("SYST:COMM:UNL")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemCommunicateUnlock() : ' \
                            +str(err))


    def SystemDate(self, year, month, day):
        """
        Sets the FS740 date if it has not been set by GPS. If the date
        has already been set by GPS, error −221, “Settings conflict,” will
        be generated and the requested date ignored.
        Manual p.129
        """
        if not np.isinstance(year, int):
            logging.warning("FS740 warning in SystemDate() : \
                             year not int")
            return
        if not np.isinstance(month, int):
            logging.warning("FS740 warning in SystemDate() : \
                             month not int")
            return
        if not np.isinstance(day, int):
            logging.warning("FS740 warning in SystemDate() : \
                             day not int")
            return
        if not ((month >= 1) and (month <= 12)):
            logging.warning("FS740 warning in SystemDate() : \
                             month out of range")
            return
        if not ((day >= 1) and (day <= 31)):
            logging.warning("FS740 warning in SystemDate() : \
                             day out of range")
            return
        try:
            self.write("SYST:DATE {0}, {1}, {2}".format(year, month, day))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemDate() : ' \
                            +str(err))

    def QuerySystemDate(self):
        try:
            return self.query("SYST:DAT?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemDate() : ' \
                            +str(err))
            return np.nan

    def SystemDisplayPower(self, period):
        """
        Sets the period of inactivity, after which the display is powered
        down.
        Manual p.129
        """
        if not period in ['NOW', 'TMIN', 'OHR', 'THR', 'ODAY', 'NEV']:
            logging.warning("FS740 warning in SystemDisplayPower() : \
                             period invalid")
            return
        try:
            self.write("SYST:DISP:POW {0}".format(period))
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in SystemDisplayPower() : ' \
                            +str(err))

    def QuerySystemDisplayPower(self):
        try:
            return self.query("SYST:DISP:POW?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning('FS740 warning in QuerySystemDisplayPower() : ' \
                            +str(err))
            return np.nan

    @WriteVisaIOError
    def SystemDisplayScreen(self, screen):
        """
        Sets the display.
        Manual p.130
        """
        if not screen in ['TBAS', 'GPS', 'COMM', 'SYST', 'SIN',
                          'AUX', 'PULS', 'MEAS1', 'MEAS2']:
            logging.warning("FS740 warning in SystemDisplayScreen() : \
                             screen invalid")
        self.write("SYST:DISP:SCR {0}".format(screen))


    @QueryVisaIOError
    def QuerySystemDisplayScreen(self):
        return self.query("SYST:DISP:SCR?")

    @WriteVisaIOError
    def SystemError(self):
        """
        Query the next error at the front of the error queue and
        then remove it.
        Manual p.130
        """
        return self.query("SYST:ERR?")

    @WriteVisaIOError
    def SystemSecurityImmediate(self):
        """
        This command wipes the instrument of user settings and
        restores the unit to factory default settings.
        Manual p.130
        """
        self.write("SYST:SEC:IMM")

    @WriteVisaIOError
    def SystemTime(self, hour, minute, second):
        """
        Sets the FS740 time of day if it has not been set by GPS.
        If the time has already been set by GPS, error −221,
        “Settings conflict,” will be generated and the requested time
        ignored. The second definition queries the current time of day.
        It returns the hour, minute, and second as a comma ( , )
        separated list of integers. The second field will be returned
        as a decimal fraction with 10 ns of resolution representing
        the precise time that the query was executed.
        Manual p.131
        """
        if not np.isinstance(hour, int):
            logging.warning("FS740 warning in SystemTime() : \
                             hour not int")
            return
        if not np.isinstance(minute, int):
            logging.warning("FS740 warning in SystemTime() : \
                             minute not int")
            return
        if not np.isinstance(second, int):
            logging.warning("FS740 warning in SystemTime() : \
                             second not int")
            return
        if not ((hour >= 0) and (hour <= 59)):
            logging.warning("FS740 warning in SystemTime() : \
                             hour out of range")
            return
        if not ((minute >= 0) and (minute <= 59)):
            logging.warning("FS740 warning in SystemTime() : \
                             minute out of range")
            return
        if not ((second >= 0) and (second <= 23)):
            logging.warning("FS740 warning in SystemTime() : \
                             hour out of range")
        self.write("SYST:TIM {0}, {1}, {2}".format(hour, minute,
                                                   second))

    @QueryVisaIOError
    def QuerySystemTime(self):
        return self.query("SYST:TIM?")

    @QueryVisaIOError
    def SystemTimePoweron(self):
        """
        Query the date and time at which the FS740 was powered on.
        Manual p.131
        """
        return self.query("SYST:TIM:POW?")



    #################################################################
    ##########  Timebase Subsystem                         ##########
    #################################################################

    """
    Not implemented:
        TBASe:CONFig:TINTerval:LIMit
        TBASe:EVENt:CLEar
        TBASe:FCONtrol:SAVe
        TBASe:TCONstant
    """
    @WriteVisaIOError
    def TBaseConfigBWidth(self, bwidth):
        """
            TBASe:CONFig:BWIDth [{AUTo|MANual}]
            TBASe:CONFig:BWIDth?
        The first definition sets the desired bandwidth control. The second
        definition queries the current value for bandwidth control. When AUTo is
        selected, the bandwidth with which the timebase follows GPS is
        automatically adjusted based on the measured timing errors. When the
        timing error is large bandwidth is increased. Conversely, when timing
        errors are small bandwidth is decreased. When MANual is selected, the
        bandwidth is fixed and the time constant of the phase lock loop is
        governed by the value set with the TBASe:TCONstant command. When the
        parameter is omitted, the value is assumed to be AUTo.
        """
        self.write("TBAS:CONF:BWID "+bwidth)

    @QueryVisaIOError
    def QueryTBaseConfigBWidth(self):
        return self.query("TBAS:CONF:BWID?")

    @WriteVisaIOError
    def TBaseConfigHMode(self, mode):
        """
            TBASe:CONFig:HMODe [{WAIT|JUMP|SLEW}]
            TBASe:CONFig:HMODe?
        The first definition controls how the timebase leaves holdover mode when
        timing offsets are larger than allowed. The second definition queries
        the current behavior for leaving holdover mode. When WAIT is selected,
        the timebase will wait for the timing offsets to improve before leaving
        holdover mode. If JUMP is selected, the timebase will leave holdover by
        jumping from its current phase to that of GPS to correct the offset
        immediately. If SLEW is selected the timebase will leave holdover by
        slewing its phase from its current value to that of GPS to correct the
        offset.
        """
        self.write("TBAS:CONF:HMOD "+mode)

    @QueryVisaIOError
    def QueryTBaseConfigHMode(self):
        return self.query("TBAS:CONF:HMOD?")

    @WriteVisaIOError
    def TBaseConfigLock(self, option):
        """
            TBASe:CONFig:LOCK [{1|ON|0|OFF}]
            TBASe:CONFig:LOCK?
        The first definition controls whether the timebase locks to GPS or not.
        When set to 1 or ON, the timebase will lock to GPS if it is generating
        timing pulses. When set to 0 or OFF, the timebase will not lock to GPS.
        If the parameter is omitted, it is assumed to be ON. The second
        definition queries the current setting.
        """
        self.write("TBAS:CONF:LOCK "+option)

    @QueryVisaIOError
    def QueryTBaseConfigLock(self):
        return self.query("TBAS:CONF:LOCK?")

    @WriteVisaIOError
    def TBaseFControl(self, fc):
        """
            TBASe:FCONtrol <fc>
            TBASe:FCONtrol?
        The first definition sets the frequency control value for the timebase
        to <fc>. The second definition returns the current frequency control
        value. Valid values may range from 0 to 4.096. Error −221,
        “Settings conflict,” is generated if the user tries to manually set the
        frequency control value when the timebase is locked to GPS. This setting
        is not automatically saved to nonvolatile memory. It must be explicitly
        saved with the TBASe:FCONtrol:SAVe command if desired.
        """
        self.write("TBAS:FCON "+fc)

    @QueryVisaIOError
    def QueryTBaseFControl(self):
        return self.query("TBAS:FCON?")

    @QueryVisaIOError
    def TBaseEventCount(self):
        """
        Query the number of events in the timebase event queue.
        Manual p.134
        """
        return self.query("TBAS:EVEN:COUN?")

    @QueryVisaIOError
    def TBaseEventNext(self):
        """
        Query the queue of timebase events for the next event.
        Manual p.134

        event : name
        =========================
        NON   : None
        POW   : Power up
        UNL   : Unlock
        SEAR  : Searching for GPS
        STAB  : Stabilizing
        VTIME : Validate time
        LOCK  : Lock
        MAN   : Manual holdover
        NGPS  : No GPS
        BGPS  : Bad GPS
        """
        return self.query("TBAS:EVEN?")

    @QueryVisaIOError
    def TBaseState(self):
        """
        Query the current state of the timebase.
        Manual p.135

        state : meaning
        ======================================
        POW   : Powered up recently
        SEAR  : Searching for GPS
        STAB  : Stabilizing timebase frequency
        VTIME : Validating GPS time of day
        LOCK  : Locked to GPS
        MAN   : Holdover at user request
        NGPS  : No GPS, in holdover
        BGPS  : Bad GPS, in holdover
        UNL   : Rb oscillator unlocked
        """
        return self.query("TBAS?")

    @QueryVisaIOError
    def TBaseStateHoldoverDuration(self):
        """
        Query the length of time in seconds the FS740 has been in
        holdover.
        Manual p.136
        """
        return self.query("TBAS:STAT:HOLD:DUR?")

    @QueryVisaIOError
    def TBaseStateLockDuration(self):
        """
        Query the length of time in seconds the FS740 has been locked
        to GPS.
        Manual p.136
        """
        return self.query("TBAS:STAT:LOCK:DUR?")

    @QueryVisaIOError
    def TBaseStateWarumpDuration(self):
        """
        Query the time in seconds that passed between when the FS740
        was powered on and it first locked to GPS.
        Manual p.136
        """
        return self.query("TBAS:WARM?")

    @WriteVisaIOError
    def TBaseTConstant(self, tconstant):
        """
            TBASe:TCONstant <time constant>
            TBASe:TCONstant? [{CURRent|TARGet|MANual}]
        The first definition sets the time constant for the phase lock loop that
        locks the timebase to GPS when MANual is selected for the command
        TBASe:CONFig:BWIDth. The second definition queries one of three
        different time constants: the current time constant, the target time
        constant, and the manual time constant set with the first definition
        above. If the parameter is omitted, the current time constant is
        returned. If the timebase is configured for automatic bandwidth control
        (the default), the current time constant may vary from 3 s up to the
        target time constant for the installed timebase. The target time
        constant is a factory setting which identifies the optimum time constant
        for the installed timebase that should be used when the timebase has
        fully stabilized and timing errors are small.
        Manual p.136
        """
        self.write("TBAS:TCON "+tconstant)

    @QueryVisaIOError
    def QueryTBaseTConstant(self, loop_time_constant = 'CURR'):
        """
        Query the the loop time constant; either CURRent, TARGet or MANual.
        Manual p.136
        """
        if not loop_time_constant in ['CURR', 'TARG', 'MAN']:
            logging.warning("FS740 warning in QueryTBaseTConstant() : \
                             loop_time_constant invalid")
        return self.query("TBAS:TCON? {0}".format(loop_time_constant))

    @WriteVisaIOError
    def TBaseConfigTIntervalLimit(self, tintlimit):
        """
            TBASe:CONFig[:TINTerval]:LIMit <time error>
            TBASe:CONFig[:TINTerval]:LIMit?
        The first definition sets the limit for timing errors to <time error> in
        seconds. The second definition queries the current limit. The
        <time error> may range from 50 ns to 1.0 s. The factory default value is
        1 μs. When the measured timing error of the timebase relative to GPS
        exceeds this limit, the timebase will unlock from GPS and enter
        holdover.
        """
        self.write("TBAS:CONF:TINT:LIM "+tintlimit)

    @QueryVisaIOError
    def QueryTBaseConfigTIntervalLimit(self):
        return self.query("TBAS:CONF:TINT:LIM?")

    @QueryVisaIOError
    def TBaseTInterval(self, average = False):
        """
        Query the current or average measured time interval in
        seconds between the internal timebase and GPS.
        Manual p.137
        """
        return self.query("TBASE:TINT? {0}".format(
            'AVER' if average else 'CURR'))

    #################################################################
    ##########  Trigger Subsystem                          ##########
    #################################################################
    """
    Commands in the Trigger Subsystem control the triggering of
    measurements. Normally when under local control, measurements are
    triggered continuously in order to provide continuous feedback
    while interacting with the instrument. Conversely, under remote
    control, measurements are only triggered when requested so that
    the data displayed corresponds closely with data retrieved.
    Commands in this subsystem enable the user to alter this behavior.
    """
    @WriteVisaIOError
    def TriggerContinuous(self, on = True):
        """
        Sets the desired trigger mode.
        Manual p.137Z
        """
        self.write("TRIG:CONT {0}".format('ON' if on else 'OFF'))

    @QueryVisaIOError
    def ReadTriggerContinuous(self):
        return self.query("TRIG:CONT?")
