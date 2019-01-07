"""
# Cryomech CPA1110

The Cryomech CPA1110 compressor supports remote monitoring through serial
(RS232/485), as well as ethernet connections, through the Modbus RTU protocol
(for serial) or ModbusTCP (for ethernet).

#### Modbus protocol

The protocol is somewhat peculiar in that it's most often only used to access
(read from or write to) 'registers' on a remote device instead of
sending/receiving more general commands. Moreover,

> Modbus protocol is defined as a master/slave protocol, meaning a device
operating as a master will poll one or more devices operating as a slave. This
means a slave device cannot volunteer information; it must wait to be asked for
it. The master will write data to a slave device's registers, and read data from
a slave device's registers. A register address or register reference is always
in the context of the slave's registers.
[[source]](https://www.csimn.com/CSI_pages/Modbus101.html)

To speed things up, I provide one command for reading out all the registers at
once; most of the other functions merely decode the registers into
human-readable data.

There are various kinds of registers defined by the Modbus standard, but the
CPA1110 only uses two kinds, namely Input and Holding Registers. The registers
used are the following [CPAxxxx Digital Panel User Manual]:

    30,001 - Operating State	
    30,002 - Compressor Running 
    30,003 - Warning State 
    30,004 - Errors
    30,005 - Alarm State 
    30,007 - Coolant In Temp 
    30,009 - Coolant Out Temp 
    30,011 - Oil Temp 
    30,013 - Helium Temp 
    30,015 - Low Pressure 
    30,017 - Low Pressure Average 
    30,019 - High Pressure 
    30,021 - High Pressure Average 
    30,023 - Delta Pressure Average 
    30,025 - Motor Current 
    30,027 - Hours Of Operation 
    30,029 - Pressure Scale 
    30,030 - Temp Scale 
    30,031 - Panel Serial Number 
    30,032 - Model Major + Minor numbers  
    30,033 - Software Rev  
    40,001 - Enable / Disable the compressor

"Modbus protocol defines a holding register as 16 bits wide; however, there is a
widely used defacto standard for reading and writing data wider than 16 bits."
[[source]](https://www.csimn.com/CSI_pages/Modbus101.html) "The first two
'Input' registers and the only 'Holding' register are 16 bit integer registers
and the rest of the input registers are in 32bit floating point format."
[CPAxxxx Digital Panel User Manual]
"""

from pymodbus.client.sync import ModbusSerialClient
import struct
import pyvisa
import time

# utility functions (see manual pp 21-22)
def to_float(b12, b34):
    return struct.unpack('f', struct.pack('H', b12)+struct.pack('H', b34))

def to_int(b12, b34):
    return struct.unpack('i', struct.pack('H', b12)+struct.pack('H', b34))


class CPA1110:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        rm = pyvisa.ResourceManager()
        COM_port = rm.resource_info(resource_name).alias
        try:
            self.client = ModbusSerialClient(method='rtu', port=COM_port,
                    stopbits = 1, bytesize = 8, parity = 'E', baudrate = 9600)
        except:
            self.verification_string = "False"
            self.client = False
            return

        # make the verification string
        self.ReadRegisters()
        self.verification_string = str(self.PanelSerialNumber()[0])

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (11, )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.client:
            self.client.close()

    def ReadValue(self):
        self.ReadRegisters()
        return [ time.time()-self.time_offset,
                 self.CoolantInTemp(),
                 self.CoolantOutTemp(),
                 self.OilTemp(),
                 self.HeliumTemp(),
                 self.LowPressure(),
                 self.LowPressureAverage(),
                 self.HighPressure(),
                 self.HighPressureAverage(),
                 self.DeltaPressureAverage(),
                 self.MotorCurrent() ]

    #################################################################
    ##########              CONTROL COMMANDS               ##########
    #################################################################

    def EnableCompressor(self):
        self.client.write_register(1, 0x0001, unit=16)

    def DisableCompressor(self):
        self.client.write_register(1, 0x00FF, unit=16)

    #################################################################
    ##########              READ COMMANDS                  ##########
    #################################################################

    def ReadRegisters(self):
        self.rr = self.client.read_input_registers(1, count=33, unit=16)

    def OperatingState(self):
        state = to_int(self.rr.registers[0], 0)
        if state == 0:
            return "Idling - ready to start"
        elif state == 2:
            return "Starting"
        elif state == 3:
            return "Running"
        elif state == 5:
            return "Stopping"
        elif state == 6:
            return "Error Lockout"
        elif state == 7:
            return "Error"
        elif state == 8:
            return "Helium Cool Down"
        elif state == 9:
            return "Power related Error"
        elif state == 15:
            return "Recovered from Error"

    def CompressorEnergized(self):
        state = to_int(self.rr.registers[1], 0)
        if state == 0:
            return "Off"
        elif state == 1:
            return "On"

    def Warnings(self):
        """
        0: No warnings 

        1: Coolant IN running High 
        2: Coolant IN running Low 
        4: Coolant OUT running High 
        8: Coolant OUT running Low 

        16:  Oil running High 
        32:  Oil running Low 
        64:  Helium running High 
        128: Helium running Low 

        256:  Low Pressure running High 
        512:  Low Pressure running Low 
        1024: High Pressure running High 
        2048: High Pressure running Low 

        4096: Delta Pressure running High 
        8192: Delta Pressure running Low 

        131072: Static Pressure running High 
        262144: Static Pressure running Low 

        524288: Cold head motor Stall

        TODO: make this work
        """
        return to_int(self.rr.registers[3], self.rr.registers[2])

    def Errors(self):
        """
        0: No Errors 

        1: Coolant IN High 
        2: Coolant IN Low 
        4: Coolant OUT High 
        8: Coolant OUT Low 

        16: Oil High 
        32: Oil Low 
        64: Helium High 
        128: Helium Low 

        256: Low Pressure High 
        512: Low Pressure Low 
        1024: High Pressure High 
        2048: High Pressure Low 

        4096: Delta Pressure High 
        8192: Delta Pressure Low 

        16384: Motor Current Low 
        32768: Three Phase Error 
        65536: Power Supply Error 

        131072: Static Pressure High 
        262144: Static Pressure Low
        """
        return to_int(self.rr.registers[3], 0)

    def CoolantInTemp(self):
        return to_float(self.rr.registers[6], self.rr.registers[7])[0]

    def CoolantOutTemp(self):
        return to_float(self.rr.registers[8], self.rr.registers[9])[0]

    def OilTemp(self):
        return to_float(self.rr.registers[10], self.rr.registers[11])[0]

    def HeliumTemp(self):
        return to_float(self.rr.registers[12], self.rr.registers[13])[0]

    def LowPressure(self):
        return to_float(self.rr.registers[14], self.rr.registers[15])[0]

    def LowPressureAverage(self):
        return to_float(self.rr.registers[16], self.rr.registers[17])[0]

    def HighPressure(self):
        return to_float(self.rr.registers[18], self.rr.registers[19])[0]

    def HighPressureAverage(self):
        return to_float(self.rr.registers[20], self.rr.registers[21])[0]

    def DeltaPressureAverage(self):
        return to_float(self.rr.registers[22], self.rr.registers[23])[0]

    def MotorCurrent(self):
        return to_float(self.rr.registers[24], self.rr.registers[25])[0]

    def HoursOfOperation(self):
        return to_float(self.rr.registers[26], self.rr.registers[27])[0]

    def PressureUnits(self):
        state = to_int(self.rr.registers[28], 0)
        if state == 0:
            return "PSI"
        elif state == 1:
            return "Bar"
        elif state == 2:
            return "KPA"

    def TemperatureUnits(self):
        state = to_int(self.rr.registers[29], 0)
        if state == 0:
            return "F"
        elif state == 1:
            return "C"
        elif state == 2:
            return "K"

    def PanelSerialNumber(self):
        return to_int(self.rr.registers[30], 0)

    def ModelNumber(self):
        """
        The upper 8 bits contain the Major model number and
        the lower 8 bits contain the Minor model number.

        Major Model Numbers consist of
            1:   800 Series
            2:   900 Series
            3:  1000 Series
            4:  1100 Series
            5:  2800 Series

        Minor Model Numbers consist of:
            1:  A1       13:  07
            2:  01       14:  H7
            3:  02       15:  I7
            4:  03       16:  08
            5:  H3       17:  09
            6:  I3       18:  9C
            7:  04       19:  10
            8:  H4       20:  1I
            9:  05       21:  11
            10: H5       22:  12
            11: I6       23:  13
            12: 06       24:  14

        Example:  A 289C compressor will give a Major of 5
        and a Minor of 18.
        """
        return to_int(self.rr.registers[31], 0)

    def SoftwareRev(self):
        return to_int(self.rr.registers[32], 0)
