import pyvisa
import time
import numpy as np
import logging

class CTC100:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.baud_rate = 9600
        self.instr.term_char = '\n'
        self.instr.read_termination = '\r\n'
        self.instr.timeout = 1000

        # make the verification string
        try:
            self.instr.write("getLog.reset")
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)
        self.verification_string = self.description()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (18, )

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        # record time
        ret_val = [ time.time() - self.time_offset ]

        # read the most recent value of all channels
        try:
            all_values = self.instr.query('getOutput?').split(",")
        except Exception as err:
            logging.warning("CTC100 warning in ReadValue(): " + str(err))
            return np.nan

        # retain the first 17 values:
        #    In 1, In 2, PCB 1, In 3, In 4, PCB 2, Out 1, Out 1 I, Out 1 V, 
        #    Out 1 R, PCB 3, Out 2, Out 2 I, Out 2 V, Out 2 R, PCB 4, AIO 1
        # discard the others:
        #    AIO 2, AIO 3, AIO 4, DIO, Relays, V1, V2, V3
        for i in range(17):
            try:
                ret_val.append(float(all_values[i]))
            except (IndexError, ValueError) as err:
                ret_val.append(np.nan)
            except Exception as err:
                logging.warning("Warning in CTC: " + str(err))

        return ret_val

    def GetWarnings(self):
        return None

    def getLog(self, channel):
        if not channel in ["In 1", "In 2", "In 3", "In 4", "Out 1", "Out 2",
                "AIO 1", "AIO 2", "AIO 3", "AIO 4", "V1", "V2", "V3", "DIO", "Relays"]:
            logging.warning("CTC100 warning in getLog(): channel doesn't exist: " + str(channel))
            return np.nan

        try:
            self.instr.write('getLog "' + channel + '", last')
            res = self.instr.read_raw()
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in getLog(): " + str(err))
            return np.nan

        if res == b'\x97\r\n': # CTC100 returns b'\x97\r\n' when it doesn't have a number to return
            return np.nan

        try:
            value = float(res)
        except ValueError:
            logging.warning("CTC100 warning in getLog(): can't convert value to float: " + str(res))
            return np.nan

        if value==0 and channel in ["In 1", "In 2", "In 3", "In 4"]:
            logging.warning("CTC100 warning in getLog(): zero temperature on channel " + str(channel))
            return np.nan
        else:
            return value

    def description(self):
        # clear instrument by attempting to read 10 messages
        self.instr.timeout = 100
        for i in range(10):
            try:
                self.instr.read()
            except pyvisa.errors.VisaIOError:
                break

        # read identification
        try:
            self.instr.write("description")
            time.sleep(1)
            val = self.instr.read_raw()
            if val == b'\x97\r\n': # CTC100 returns b'\x97\r\n' when it doesn't have a number to return
                return "False"
            else:
                try:
                    return val.decode('utf-8')
                except UnicodeDecodeError as err:
                    logging.warning("CTC100 getting identification failed: ", err)
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in description(): " + str(err))
            return np.nan

    def outputStatus(self):
        try:
            self.instr.write("outputEnable?")
            time.sleep(1)
            val = self.instr.read_raw()
            if val == b'\x97\r\n': # CTC100 returns b'\x97\r\n' when it doesn't have a number to return
                return "False"
            else:
                try:
                    return val.decode('utf-8')
                except UnicodeDecodeError as err:
                    logging.warning("CTC100 getting output status failed: ", err)
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in OutputStatus(): " + str(err))
            return np.nan

    def OutputStatusReport(self):
        try:
            values = self.ReadValue()
            out1, out2 = values[7], values[12]
            if (out1>0) or (out2>0):
                return "On"
            else:
                return "Off"
        except Exception as err:
            logging.error("Error in CTC100: "+str(err))
            return "invalid"

    def outputEnable(self):
        try:
            return self.instr.write("outputEnable on")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in outputEnable(): " + str(err))
            return np.nan

    def outputDisable(self):
        try:
            return self.instr.write("outputEnable off")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in outputDisable(): " + str(err))
            return np.nan

    def setADrate(self, rate):
        if not rate in [ "16.7 ms", "33.3", "50 ms", "66.7 ms", "83.3 ms", "100 ms",
                 "150 ms", "200 ms", "250 ms", "350 ms", "400 ms", "500 ms",
                 "600 ms", "700 ms", "800 ms", "900 ms", "1000 ms"]:
            logging.warning("CTC100 warning in setADrate(): invalid A/D rate: " + str(rate))
            return np.nan
        else:
            try:
                return self.instr.write('"system.other.A/D rate" "' + rate + '"')
            except pyvisa.errors.VisaIOError as err:
                logging.warning("CTC100 warning in setADrate(): " + str(err))
                return np.nan

    def setLogRate(self, rate):
        if not rate in ["off", "0.1 s", "0.3 s", "1 s", "3 s", "10 s", "30 s",
                "1 min", "3 min", "10 min", "30 min", "1 hr"]:
            logging.warning("CTC100 warning in setLogRate(): invalid logging rate: " + str(rate))
            return np.nan
        else:
            try:
                return self.instr.write('"system.log.interval" "' + rate + '"')
            except pyvisa.errors.VisaIOError as err:
                logging.warning("CTC100 warning in setLogRate(): " + str(err))
                return np.nan

    def SetOut1Setpoint(self, setpoint):
        # sanity check for the setpoint
        try:
            float(setpoint)
        except ValueError as err:
            logging.warning("CTC100 warning in SetOut1Setpoint(): " + str(err))

        try:
            return self.instr.write('"Out1.PID.Setpoint" "' + str(setpoint) + '"')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut1Setpoint(): " + str(err))
            return np.nan

    def SetOut2Setpoint(self, setpoint):
        # sanity check for the setpoint
        try:
            float(setpoint)
        except ValueError as err:
            logging.warning("CTC100 warning in SetOut2Setpoint(): " + str(err))

        try:
            return self.instr.write('"Out2.PID.Setpoint" "' + str(setpoint) + '"')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut2Setpoint(): " + str(err))
            return np.nan

    def SetOut1Src(self, src):
        try:
            return self.instr.write('"Out1.PID.Input" "' + src + '"')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut1Src(): " + str(err))
            return np.nan

    def SetOut2Src(self, src):
        try:
            return self.instr.write('"Out2.PID.Input" "' + src + '"')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut2Src(): " + str(err))
            return np.nan

    def SetOut1P(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("CTC100 warning in SetOut1P(): invalid parameter " + str(param))
            return np.nan

        try:
            return self.instr.write('Out1.PID.P ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut1P(): " + str(err))
            return np.nan

    def SetOut1I(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("CTC100 warning in SetOut1I(): invalid parameter " + str(param))
            return np.nan

        try:
            return self.instr.write('Out1.PID.I ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut1I(): " + str(err))
            return np.nan

    def SetOut1D(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("CTC100 warning in SetOut1D(): invalid parameter " + str(param))
            return np.nan

        try:
            return self.instr.write('Out1.PID.D ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut1D(): " + str(err))
            return np.nan

    def SetOut2P(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("CTC100 warning in SetOut2P(): invalid parameter " + str(param))
            return np.nan

        try:
            return self.instr.write('Out2.PID.P ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut2P(): " + str(err))
            return np.nan

    def SetOut2I(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("CTC100 warning in SetOut2I(): invalid parameter " + str(param))
            return np.nan

        try:
            return self.instr.write('Out2.PID.I ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut2I(): " + str(err))
            return np.nan

    def SetOut2D(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("CTC100 warning in SetOut2D(): invalid parameter " + str(param))
            return np.nan

        try:
            return self.instr.write('Out2.PID.D ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("CTC100 warning in SetOut2D(): " + str(err))
            return np.nan
