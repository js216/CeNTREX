from pysnmp.hlapi import *
import time
import datetime as dt
import logging
import numpy as np

class Vertiv:
    def __init__(self,  time_offset, connection):
        self.time_offset = time_offset
        self.host = connection['host']
        self.community = connection['community']
        self.trap = int(connection['trap'])
        self.warnings = []
        self.new_attributes = []
        self.dtype = 'f'
        self.shape = (19,1)
        self.verification_string = self.VerifyOperation()
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return

    def ReadValue(self):
        conv = [float, float, float, float, int, int, int, int, float,
                float, float, float, int, float, int, float, float, int]

        # commands retrieve data for:
        # returnTemperature, returnHumidity, returnDewPoint, supplyTemperature, coolingCapacity, dehumCapacity, humCapacity,
        # fanCapacity, tempSetPoint, tempDeadBand, tempPropBand, tempIntegrationTime, humSetPoint, humDeadBand, humPropBand,
        # humIntegrationTime, fanSpeedTempSetPoint, hotWater/hotGas Valve
        commandsLog = ['1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.4291', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5028',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5004', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5002',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5490', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5079',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5081', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5077',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5008', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5011',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5325', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5326',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5029', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5032',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5341', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5342',
               '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5585', '1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5380']
        values = self.queryMultiple(commandsLog)
        values = [c(v) if v != b'Unavailable' else 0 for c,v in zip(conv, values)]
        return [time.time()-self.time_offset]+values

    def GetWarnings(self):
        return []

    def VerifyOperation(self):
        return self.GetSystemModel()

    def query(self, cmd):
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(SnmpEngine(),
            CommunityData(self.community),
            UdpTransportTarget((self.host, self.trap)),
            ContextData(),
            ObjectType(ObjectIdentity(cmd)))
        )
        if errorIndication:
            logging.warning("Vertiv warning in query: {0}".format(errorIndication))
            return np.nan
        elif errorStatus:
            logging.warning("Vertiv warning in query: {0} at {1}".format(errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
            return np.nan
        else:
            name, value = varBinds[0]
            return value

    def queryMultiple(self, cmds):
        OTypes = [ObjectType(ObjectIdentity(c)) for c in cmds]
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(SnmpEngine(),
            CommunityData(self.community),
            UdpTransportTarget((self.host, self.trap)),
            ContextData(),
            *OTypes)
        )
        if errorIndication:
            logging.warning("Vertiv warning in queryMultiple: {0}".format(errorIndication))
            return np.nan
        elif errorStatus:
            logging.warning("Vertiv warning in query: {0} at {1}".format(errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
            return np.nan
        else:
            names, values = [], []
            for varBind in varBinds:
                name, value = varBind
                names.append(name)
                values.append(value)
            return values

    def GetSystemModel(self):
        """
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.2.1.2.0'))

    def GetSystemModelNumber(self):
        """

        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.3.20.1.4240'))

    def GetSystemStatus(self):
        """
        System Status
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.3.20.1.4123'))

    def GetUnitControlMode(self):
        """
        Unit Control Mode
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.4707'))

    #################################################################
    ##########  Unit State                                 ##########
    #################################################################

    def GetSystemState(self):
        """
        System State
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.7.2.2.0'))

    def GetUnitOperatingState(self):
        """
        Unit Operating State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.4706'))

    def GetUnitCoolingState(self):
        """
        Unit Cooling State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5382'))

    def GetCompressorState(self, compressor = 1):
        """
        Compressor State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5264.{0}'.format(compressor)))

    def GetFanState(self):
        """
        Fan State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5381'))

    def GetFreeCoolingState(self):
        """
        Free Cooling State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5383'))

    def GetHotWaterHotGasState(self):
        """
        Hot Water / Hot Gas State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5385'))

    def GetElectricReheaterState(self):
        """
        Electric Reheater State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5386'))

    def GetDehumidiferState(self):
        """
        Dehumidifier State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5387'))

    def GetHumidifierState(self):
        """
        Humidifier State
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5388'))

    def GetStateCoolingCapacity(self):
        """
        State Cooling Capacity
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.4.3.9.0'))

    def GetStateHeatingCapacity(self):
        """
        State Heating Capacity
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.4.3.10.0'))

    def GetStateFanCapacity(self):
        """
        State Fan Capacity
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.4.3.16.0'))

    def GetStateDehumidifyingCapacity(self):
        """
        State Dehumidifying Capacity
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.4.3.18.0'))

    def GetStateHumidifyingCapacity(self):
        return int(self.query('1.3.6.1.4.1.476.1.42.3.4.3.19.0'))

    #################################################################
    ##########  Return Sensor                              ##########
    #################################################################

    def GetReturnAirTemperature(self):
        """
        Return Sensor Air Temperature in Celcius
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.4291'))

    def GetReturnDewPoint(self):
        """
        Return Sensor Dew Point
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5004'))

    def GetReturnHumidity(self):
        """
        Return Sensor Humidity
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5028'))


    #################################################################
    ##########  Supply Sensor                              ##########
    #################################################################

    def GetSupplyAirTemperature(self):
        """
        Supply Sensor Air Temperature in Celcius
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5002'))



    #################################################################
    ##########  Read Control Parameters                    ##########
    #################################################################

    def GetAirTemperatureControlType(self):
        """
        Air Temperature Control Type
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5324'))

    def GetAirTemperatureSetPoint(self):
        """
        Air Temperature Set Point
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5008'))

    def GetAirTemperatureDeadBand(self):
        """
        Air Temperature Dead Band
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5011'))

    def GetAirTemperatureProportionalBand(self):
        """
        Air Temperature Proportional Band
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5325'))

    def GetAirTemperatureIntegrationTime(self):
        """
        Air Temperature Integration Time
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5326'))

    def GetDewPointSetPoint(self):
        """
        Dew Point Set Point
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5575'))

    def GetHumidityControlType(self):
        """
        Humidity Control Type
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5603'))

    def GetHumiditySetPoint(self):
        """
        Humidity Set Point
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5029'))

    def GetHumidityDeadBand(self):
        """
        Humidity Dead Band
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5032'))

    def GetHumidityProportionalBand(self):
        """
        Humidity Proportional Band
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5341'))

    def GetHumidityIntegrationTime(self):
        """
        Humidity Integration Time
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5342'))

    def GetFanSpeedTemperatureSetPoint(self):
        """
        Fan Speed Temperature SetPoint
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5585'))


    #################################################################

    def GetFanCapacity(self):
        """
        Fan Capacity
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.4.3.16.0'))

    def GetFanSpeed(self):
        """
        Fan Speed Percentage
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5077'))

    def GetDehumidifierUtilization(self):
        """
        Dehumidifier Utilization Percentage
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5079'))

    def GetHumidifierUtilization(self):
        """
        Humidifer Utilization Percentage
        """
        return int(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5081'))

    def GetCoolingCapacity(self):
        """
        Cooling Capacity Percentage
        """
        return str(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5490'))

    def GetAdjustedHumidity(self):
        """
        Adjusted Humidity
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5606'))

    def GetExternalDewPointOverTemperatureThreshold(self):
        """
        External Dew Point Over Temp Threshold
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.4614'))

    def GetExternalDewPointUnderTemperatureThreshold(self):
        """
        External Dew Point Under Temperature Threshold
        """
        return float(self.query('1.3.6.1.4.1.476.1.42.3.9.20.1.20.1.2.1.5576'))
