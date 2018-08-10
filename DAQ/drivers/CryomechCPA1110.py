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
it. The master will write data to a slave device’s registers, and read data from
a slave device’s registers. A register address or register reference is always
in the context of the slave’s registers.
[[source]](https://www.csimn.com/CSI_pages/Modbus101.html)

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

import pymodbus

class CPA1110:
    def __init__(self, resource_name):
        self.client = client.sync.ModbusSerialClient(
            method='rtu', port='COM4')

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        self.client.close()
        pass
    
    # TODO: implement the correct data conversions.
    
    def read_float32(self, count):
        return self.client.read_input_registers(ref, count=count)
    
    def read_integer32(self, count):
        return self.client.read_input_registers(ref, count=count)
    
    #################################################################
    ##########              CONTROL COMMANDS               ##########
    #################################################################
    
    def EnableCompressor(self):
        self.client.write_register(40001, 0x00FF)
    
    def DisableCompressor(self):
        self.client.write_register(40001, 0x00FF)
    
    #################################################################
    ##########              READ COMMANDS                  ##########
    #################################################################
    
    def CompressorEnabled(self):
        """
        0x00FF - Turn the compressor OFF 
        0x0001 - Turn the compressor ON 
        """
        return self.client.read_holding_registers(40001)
    
    def OperatingState(self):
        """
        0: Idling - ready to start 
        2: Starting 
        3: Running 
        5: Stopping 
        6: Error Lockout 
        7: Error 
        8: Helium Cool Down 
        9: Power related Error 
        15: Recovered from Error 
        """
        return self.client.read_input_registers(30001)
    
    def CompressorEnergized(self):
        """
        0: Off
        1: On
        """
        return self.client.read_input_registers(30002)
    
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
        """
        return self.read_integer32(40003)
        
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
        return self.read_integer32(40004)
    
    def AlarmState(self):
        return self.read_float32(40005)
    
    def CoolantInTemp(self):
        return self.read_float32(40007)
    
    def CoolantOutTemp(self):
        return self.read_float32(40009)
    
    def OilTemp(self):
        return self.read_float32(40011)
    
    def HeliumTemp(self):
        return self.read_float32(40013)
    
    def LowPressure(self):
        return self.read_float32(40015)
    
    def LowPressureAverage(self):
        return self.read_float32(40017)
    
    def HighPressure(self):
        return self.read_float32(40019)
    
    def HighPressureAverage(self):
        return self.read_float32(40021)
    
    def DeltaPressureAverage(self):
        return self.read_float32(40023)
    
    def MotorCurrent(self):
        return self.read_float32(40025)
    
    def HoursOfOperation(self):
        return self.read_float32(40027)
    
    def PressureUnits(self):
        """
        0: PSI
        1: Bar
        2: KPA
        """
        return self.read_integer32(40029)
    
    def TemperatureUnits(self):
        """
        0: Fahrenheit
        1: Celsius
        2: Kelvin
        """
        return self.read_integer32(40030)
    
    def PanelSerialNumber(self):
        return self.read_integer32(40031)
    
    def ModelNumber(self):
        """
        The upper 8 bits contain the Major model number and
        the lower 8 bits contain the Minor model number.

        Major Model Numbers consist of
            1:   800 Series
            2:   900 Series
            3:  1000 Series
            4:  1100 Series
            5:  2800 Series

        Minor Model Numbers consist of:
            1:  A1       13:  07
            2:  01       14:  H7
            3:  02       15:  I7
            4:  03       16:  08
            5:  H3       17:  09
            6:  I3       18:  9C
            7:  04       19:  10
            8:  H4       20:  1I
            9:  05       21:  11
            10: H5       22:  12
            11: I6       23:  13
            12: 06       24:  14

        Example:  A 289C compressor will give a Major of 5
        and a Minor of 18.
        """
        return self.read_integer32(40032)
    
    def SoftwareRev(self):
        return self.read_integer32(40033)
