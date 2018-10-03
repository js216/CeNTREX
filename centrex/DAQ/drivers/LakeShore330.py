import visa

class LakeShore330:
    def __init__(self, rm, resource_name):
        self.rm = rm
        self.instr = self.rm.open_resource(resource_name)

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        self.instr.close()
    
    #################################################################
    ##########              COMMON COMMANDS                ##########
    #################################################################
    ## Common commands are input/output commands defined by the    ##
    ## IEEE-488 standard and are shared with other instruments     ##
    ## complying with the standard. Common commands begin with an  ##
    ## asterisk (*).                                               ##
    #################################################################
    
    def ClearInterfaceCommand(self):
        """Clears the bits in the Status Byte Register and Standard
        Event Status Register and terminates all pending operations.
        Clears the interface, but not the controller. The controller
        related command is *RST.
        
        Returns: Nothing.
        """
        self.instr.write("*CLS")

    def ConfigureStatusReportsSESR(self, bit_weighting):
        """Configure Status Reports in the Standard Event Status Register.
        
        Each bit is assigned a bit weighting and represents the
        enable/disable status of the corresponding event flag bit in the
        Standard Event Status Register. To enable an event flagbit, send
        the command *ESE with the sum of the bit weighting for each desired
        bit. See the*ESR? command for a list of event flags. 
        
        Returns: Nothing.
        """
        self.instr.write("*ESE "+str(bit_weighting))

    def QueryStatusReportsConfiguration(self):
        """Query the Configuration of Status Reports in the Standard Event
        Status Register.
        
        The integer returned represents the sum of the bit weighting of the
        enable bits in the Standard Event Status Enable Register.
        
        Returns:
        <ESE bit weighting>. Format: nnn[term]
        """
        return self.instr.query("*ESE?")
    
    def QueryStandardEventStatusRegister(self):
        """Queries for various Model 330 error conditions and status.
        The integer returned represents the sum of the bit weighting
        of the event flag bits in the Standard Event Status Register.
        
        Returns:
        <ESR bit weighting>. Format: nnn[term]
        """
        return self.instr.query("*ESR?")

    def QueryIdentification(self):
        """Identifies the instrument model and software level.
        
        Returns:
        <manufacturer>, <model number>, <serial number>, <firmware date>
        Format: LSCI,MODEL330,aaaaaa,nnnnnn[term]
        """
        return self.instr.query("*IDN?")
    
    def OperationCompleteCommand(self):
        """Generates an Operation Complete event in the Event Status
        Register upon completion of all pending selected device operations.
        Send it as the last command in a command string.
        
        Returns: Nothing.
        """
        self.instr.write("*OPC")
    
    def QueryOperationComplete(self):
        """Places a '1' in the controller output queue upon completion
        of all pending selected device operations. Send as the last
        command in a command string. Not the same as *OPC. 
        
        Returns:
        1. Format: n[term]
        """
        return self.instr.query("*OPC?")
        
    def ResetInstrument(self):
        """Sets controller parameters to power-up settings.
        
        Returns: Nothing.
        """
        self.instr.write("*RST")
        
    def ConfigureStatusReportsSRER(self, bit_weighting):
        """Configure Status Reports in the Service Request Enable Register.
        
        Each bit has a bit weighting and represents the enable/disable
        status of the corresponding status flag bit in the Status Byte
        Register. To enable a status flag bit, send the command *SRE
        with the sum of the bit weighting for each desired bit. See
        the *STB? command for a list of status flags. 
        
        Returns: Nothing.
        """
        self.instr.write("*SRE "+str(bit_weighting))
    
    def QueryServiceRequestEnableRegister(self):
        """The integer returned represents the sum of the bit weighting
        of the enabled bits in the Service Request Enable Register.
        See the *STB? command for a list of status flags.
        
        Returns:
        <SRE bit weighting>. Format: nnn[term]
        """
        return self.instr.query("*SRE?")
    
    def QueryStatusByte(self):
        """Acts like a serial poll, but does not reset the register to
        all zeros. The integer returned represents the sum of the bit
        weighting of the status flag bits that are set in the Status
        Byte Register. 
        
        Returns:
        <STB bit weighting>. Format: nnn[term]
        """
        return self.instr.query("*STB?")
    
    def QuerySelfTest(self):
        """The Model 330 performs a self-test at power-up.
        0 = no errors found, 1 = errors found.
        
        Returns:
        0 or 1. Format: n[term]
        """
        return self.instr.write("*TST?")
    
    def WaitToContinue(self):
        """Prevents execution of any further commands or queries until
        completion of all previous ones. Changing the sample sensor and
        reading it immediately with a device dependent query may result
        in a reading error because the sensor needs time to stabilize.
        Place a *WAI between the sensor change and query for a correct
        reading. Achieve the same results with repeated queries or using
        a Service Request, but *WAI is easier. Send *WAI as the last
        command in a command string followed by appropriate termination.
        It cannot be embedded between other commands.

        Returns: Nothing.
        """
        self.instr.write("*WAI")
    
    #################################################################
    ##########              INTERFACE COMMANDS             ##########
    #################################################################
    
    def SetAddress(self, address):
        """Sets the IEEE address. The Model 330 is factory preset to 12.

        Returns: Nothing.
        """
        self.instr.write("ADDR "+str(address))
    
    def QueryAddress(self):
        """Returns the current IEEE address setting. The Model 330 is
        factory preset to 12. 
        
        Returns: 1 to 30.
        """
        self.instr.query("ADDR?")

    def SetEOIStatus(self, status):
        """Set End Or Identify (EOI) Status.
        
        Sets the EOI status: 0 = enabled, 1 = disabled. When enabled,
        the hardware EOI line becomes active with the last byte of a
        transfer. The EOI identifies the last byte allowing for variable
        length data transmissions. 

        Returns: Nothing.
        """
        self.instr.write("END "+str(status))
        
    def QueryEOIStatus(self):
        """End Or Identify (EOI) Status Query.
        
        Returns:
        Current EOI status: 0 = EOI enabled, 1 = EOI disabled
        """
        self.instr.query("END?")
        
    def Mode(self, mode):
        """Set Local, Remote, or Remote With Local Lockout Mode.
        
        Sets the Model 330 mode:
           0 = Local Mode,
           1 = Remote Mode,
           2 = Remote Mode with Local Lockout.
        Press the front panel Local key to set the Model 330 to local
        provided the key has not been disabled by local lockout. The
        Model 330 powers up in local mode.
        
        Returns: Nothing.
        """
        self.instr.write("MODE "+str(mode))
        
    def ModeQuery(self):
        """
        Returns: Current mode setting:
           0 = local mode,
           1 = remote mode,
           2 = remote mode with local lockout.
        """
        return self.instr.query("MODE?")

    def SetTerminatingCharacterType(self, term):
        """Sets the terminating character type from 0 to 3
        defined as follows:
        
            0 = Carriage return and line feed (CR)(LFEOI)
            1 = Line feed and carriage return (LF)(CREOI)
            2 = Line feed (LFEOI)
            3 = No terminating characters 
            
            EOI line set with last data
                byte if enabled (End) Terminating characters are sent when
                the Model 330 completes its message transfer on output.
                They  also identify the end of an input message. This
                command works only with the IEEE-488 Interface and does
                not change the serial terminators.
            
        Returns: Nothing.
        """
        self.instr.write("TERM "+str(term))
        
    def TerminatorQuery(self):
        """Terminator Query.
        
        This command works only with the IEEE-488 Interface. 
        
        Returns: the current terminating character type:
            0 = Carriage return and line feed (CR)(LFEOI)
            1 = Line feed and carriage return (LF)(CREOI)
            2 = Line feed (LFEOI)
            3 = No terminating characters 
            
            EOI line set with last data byte if enabled (End) 
        """
        return self.instr.query("TERM?")
    
    #################################################################
    ##########              DISPLAY COMMANDS               ##########
    #################################################################
    ## Display commands allow the interface to act as a virtual    ##
    ## display. Transfer display data, as well as format.          ##
    #################################################################
    
    def SetControlChannel(self, channel):
        """Set Control Channel to A or B.
        
        Sets control channel to sensor A or B. Do not combine channel,
        control unit, and setpoint changes. Allow one controller update
        cycle (1/2 second) between these commands so the Model 330
        interprets them correctly.
        
        Returns: Nothing.
        """
        self.instr.write("CCHN "+channel)
        
    def ControlChannelQuery(self):
        """Returns the current control channel setting: A = channel A,
        B = channel B.
        
        Returns: A or B
        """
        return self.instr.query("CCHN?")
    
    def ControlSensorDataQuery(self):
        """Returns control sensor data. A free field is active here.
        The value returned is 7 characters: a sign, 5 digits and a
        decimal point. The last digit may be a null. 
        
        Returns: +/-000.00
        """
        return self.instr.query("CDAT?")
    
    def SetControlChannelUnits(self, units):
        """Set control channel units: K = kelvin, C = Celsius,
        S = appropriate sensor units (volts, ohms, or millivolts).
        
        Returns: Nothing.
        """
        self.instr.write("CUNI "+units)

    def ControlUnitsQuery(self):
        """Current control units setting: K = kelvin, C = Celsius,
        V = volts, R = Ohms, M = millivolts. 
        
        Returns: K, C, V, R, or M
        """
        return self.instr.query("CUNI?")

    def SetDisplayFilter(self, filt):
        """Turns display filter on or off: 0 = Off, 1 = On.
        Quiets display by taking a running average of 10 readings. 
        
        Returns: Nothing.
        """
        self.instr.write("FILT "+str(filt))

    def DisplayFilterQuery(self):
        """Returns display filter setting: 0 = Off, 1 = On.
        
        Returns: 0 or 1
        """
        return self.instr.query("FILT?")

    def SetSampleChannel(self, channel):
        """Set Sample Channel to A or B.
        
        Sets the sample channel to sensor A or B. Allow one controller
        update cycle (1/2 second) before reading the sample data to ensure
        proper reading.
        
        Returns: Nothing.
        """
        self.instr.write("SCHN "+channel)
        
    def SampleChannelQuery(self):
        """Returns the current sample channel setting: A = channel A,
        B = channel B. 
        
        Returns: A or B
        """
        return self.instr.query("SCHN?")
    
    def SampleSensorDataQuery(self):
        """Returns sample sensor data. A free field is active here.
        The value returned is 7 characters: a sign, 5 digits and a
        decimal point. The last digit may be a null.
        
        Returns: +/-000.00
        """
        return self.instr.query("SDAT?")
    
    def SetSampleChannelUnits(self, channel):
        """Set Sample Channel to A or B.
        
        Sets the sample channel to sensor A or B. Allow one controller
        update cycle (1/2 second) before reading the sample data to ensure
        proper reading.
        
        Returns: Nothing.
        """
        self.instr.write("SUNI"+channel)
        
    def SampleUnitsQuery(self):
        """Current sample units setting: K = kelvin, C = Celsius,
        V = volts, R = Ohms, M = millivolts. 
        
        Returns: K, C, V, R, or M
        """
        return self.instr.query("SUNI?")
    
    #################################################################
    ##########              CONTROL PROCESS COMMANDS       ##########
    #################################################################
    ## Control Process Commands allow the interface to change any  ##
    ## of the Model 330 control parameters. Access Manual mode PID ##
    ## parameters as well as Autotuning status.                    ##
    #################################################################
    
    def SetControlLimitBand(self, limit):
        """Set Control Limit Band for Control Sensor.
        
        Sets the control limit band for the control sensor. Enter a value
        from 0 to 999.9. Used in conjunction with the Service Request
        function. It utilizes the free field format. See the Status
        Byte Register and the Control Limit Exceeded Bit (Bit 2)
        discussions. 
        
        Returns: Nothing.
        """
        self.instr.write("CLIM"+str(limit))
        
    def ControlLimitQuery(self):
        """Returns the control limit setting.
        
        Returns: XXX.X (a number from 0 to 999.9)
        """
        return self.instr.query("CLIM?")

    def SetGain(self, gain):
        """Set Gain While In Manual Control Mode
        
        Enter an integer from 0 to 999. Gain corresponds to the
        Proportional (P) portion of the PID Autotuning control algorithm. 
        
        Returns: Nothing.
        """
        self.instr.write("GAIN"+str(gain))
        
    def GainQuery(self):
        """Returns current gain setting in manual or AutoTune mode.
        Gain corresponds to the Proportional (P) portion of the PID
        Autotuning control algorithm. 
        
        Returns: XXX (a number from 000 to 999)
        """
        return self.instr.query("GAIN?")
    
    def HeaterPowerStatusQuery(self):
        """Returns the percent of full scale heater current.
        The returned number represents five percent increments up to 100.
        
        Returns: XXX
        """
        return self.instr.query("HEAT?")
    
    def SetRampFunction(self, fn):
        """RAMP 0 disables the ramping function while RAMP 1 enables
        ramping.  
        
        Returns: Nothing.
        """
        self.instr.write("RAMP"+str(fn))

    def RampingEnableDisableStatusQuery(self):
        """Returns Ramp status: 0 = ramping function disabled,
        1 = ramping function enabled. 
        
        Returns: 0 or 1
        """
        return self.instr.query("RAMP?")
    
    def SetRampRate(self, rate):
        """Set Ramp Rate in Kelvin per Minute.
        
        XX.X is the ramp rate in Kelvin per minute between 0 and 99.9. 
        
        Returns: Nothing.
        """
        self.instr.write("RAMPR"+str(rate))
        
    def RampRateQuery(self):
        """Returns the current value of the ramp rate.
        
        Returns: XX.X
        """
        return self.instr.query("RAMPR?")
    
    def RampingStatusQuery(self):
        """Returns 1 if controller is ramping or 0 if not ramping.
        
        Returns: 0 or 1
        """
        return self.instr.query("RAMPS?")
    
    def SetHeaterStatus(self, status):
        """Sets heater status: 0 = off, 1 = low, 2 = medium, 3 = high. 
        
        XX.X is the ramp rate in Kelvin per minute between 0 and 99.9. 
        
        Returns: Nothing.
        """
        self.instr.write("RANG"+str(status))

    def HeaterStatusQuery(self):
        """Returns current heater status: 0 = off, 1 = low, 2 = medium,
        3 = high. 
        
        Returns: 0, 1, 2, or 3
        """
        return self.instr.query("RANG?")
    
    def SateManualModeRate(self, rate):
        """Enter an integer from 0 through 200. Rate corresponds to
        the Differential (D) portion of the PID Autotuning control
        algorithm. 
        
        Returns: Nothing.
        """
        self.instr.write("RATE"+str(rate))

    def RateQuery(self):
        """Returns current rate setting. Rate corresponds to the
        Differential (D) portion of the PID Autotuning control algorithm.
        
        Returns: XXX (Integer from 0 to 200)
        """
        return self.instr.query("RATE?")
    
    def SetManualModeReset(self, reset):
        """Enter an integer from 0 to 999. Reset corresponds to the
        Integral (I) portion of the PID Autotuning control algorithm. 
        
        Returns: Nothing.
        """
        self.instr.write("RSET"+str(reset))
        
    def ResetQuery(self):
        """Returns current reset setting. Reset corresponds to the
        Integral (I) portion of the PID Autotuning control algorithm.
        
        Returns: XXX (Integer from 0 to 999)
        """
        return self.instr.query("RSET?")
    
    def SetSetpoint(self, setpoint):
        """Sets the Setpoint In Units Chosen For Control Channel.
        
        For the setpoint parameter, enter a value from 0 to 999.9 for
        temperature or 0 to 2.4990 for voltage. Utilizes the free field
        format. Resolution is 0.01 for temperatures below 200.
        
        Returns: Nothing.
        """
        self.instr.write("SETP"+str(setpoint))
        
    def SetpointStatusQuery(self):
        """Returns current set point setting, a 7-digit value (a sign,
        5 digits, and a decimal point). Resolution is 0.01 for
        temperatures below 200.
        
        Returns:
        +/-XXX.X for temperature, or +/-X.XXXX for voltage
        """
        return self.instr.query("SETP?")
    
    def SetAutotuningStatus(self, status):
        """Sets Autotuning status: 0 = Manual, 1 = P, 2 = PI, 3 = PID,
        4 = Zone. See Paragraph 3.3.4 for details on Autotuning settings. 
        
        Returns: Nothing.
        """
        self.instr.write("TUNE"+str(status))
        
    def AutotuningQuery(self):
        """Returns current Autotuning status: 0 = Manual, 1 = P, 2 = PI,
        3 = PID, 4 = Zone. See Paragraph 3.3.4 for details on Autotuning
        settings.
        
        Returns: X
        """
        return self.instr.query("TUNE?")
    
    def ZoneStorage(self, zone):
        """Stores the stated values of Setpoint, Heater Range, Gain, Rate,
        and Reset. Zone XX is between 01 and 10. +/-SSS.S = setpoint in
        kelvin, R = heater range, PPP = gain, III = Reset, DDD = Rate.
        For Heater Range: 0 = Heater off, 1 = Heater Low, 2 = Heater Medium,
        3 = Heater High. Use the TUNE command to activate the zone
        autotuning mode.
        
        Example: ZONE 1,100.0,2,100.0,100,20[term]
        instructs the Model 330 to store in Zone 1 a 100.0 K setpoint,
        a 2 (Medium) Heater Range, a 100 Gain, a 100 Reset, and a 20% Rate.
        
        Returns: Nothing.
        """
        self.instr.write("ZONE"+zone)
        
    def ZoneStorageQuery(self):
        """When entering the zone command, XX defines the zone between
        01 and 10.
        
        Returns:
        +/-SSS.S,R,PPP,III,DDD where
        +/-SSS.S = setpoint in kelvin, R = heater range, PPP = gain,
        III = Reset, DDD = Rate. For Heater Range: 0 = Heater off,
        1 = Heater Low, 2 = Heater Medium, 3 = Heater High. Use TUNE
        command to activate zone autotuning mode.
        """
        return self.instr.query("ZONE?")
    
    #################################################################
    ##########              CURVE COMMANDS                 ##########
    #################################################################
    ## Curve Commands allow users to verify existing factory-added ##
    ## curves or enter or delete user-defined curves over the      ##
    ## interface.                                                  ##
    #################################################################
    
    def SetRoomTemperatureCompensationChannelA(self, comp):
        """Effective only with the Model 330-4X Thermocouple Version.
        Select temperature compensation parameter: 0 = off, 1 = on. 
        
        Returns: Nothing.
        """
        self.instr.write("ACOMP"+comp)
        
    def QueryRoomTemperatureCompensationChannelA(self):
        """Effective only with the Model 330-4X Thermocouple Version.
        Returns current room temperature compensation status: 0 = off,
        1 = on.
        
        Returns: 0 or 1
        """
        return self.instr.query("ACOMP?")
    
    def AssignCurveNumberChannelA(self, number):
        """Effective only with the Model 330-4X Thermocouple Version.
        Select temperature compensation parameter: 0 = off, 1 = on. 
        
        Returns: Nothing.
        """
        self.instr.write("ACUR"+number)
        
    def QueryCurveNumberChannelA(self):
        """Returns the currently selected sensor curve number for
        Channel A. Table 3-1 lists sensor curve numbers. 
        
        Returns: XX (an integer from 00 to 31)
        """
        return self.instr.query("ACUR?")
        
    def ChannelAInputTypeQuery(self):
        """Returns input type for Channel A: SI = silicon diode,
        PT = platinum, AS = GaAlAs, TC = thermocouple, ER = error
        (improper switch setting).
        
        Returns: SI, PT, AS, TC, or ER
        """
        return self.instr.query("ATYPE?")
    
    def SetRoomTemperatureCompensationChannelB(self, comp):
        """Effective only with the Model 330-4X Thermocouple Version.
        Select temperature compensation parameter: 0 = off, 1 = on. 
        
        Returns: Nothing.
        """
        self.instr.write("BCOMP"+comp)
        
    def QueryRoomTemperatureCompensationChannelB(self):
        """Effective only with the Model 330-4X Thermocouple Version.
        Returns current room temperature compensation status: 0 = off,
        1 = on.
        
        Returns: 0 or 1
        """
        return self.instr.query("BCOMP?")
    
    def AssignCurveNumberChannelB(self, number):
        """Enter an integer from 0 through 31 for Channel B.
        Table 3-1 lists sensor curve numbers. 
        
        Returns: Nothing.
        """
        self.instr.write("BCUR"+number)
        
    def QueryCurveNumberChannelB(self):
        """Returns the currently selected sensor curve number for
        Channel B. Table 3-1 lists sensor curve numbers. 
        
        Returns: XX (an integer from 00 to 31)
        """
        return self.instr.query("BCUR?")
        
    def ChannelBInputTypeQuery(self):
        """Returns input type for Channel B: SI = silicon diode,
        PT = platinum, AS = GaAlAs, TC = thermocouple, ER = error
        (improper switch setting).
        
        Returns: SI, PT, AS, TC, or ER
        """
        return self.instr.query("BTYPE?")
    
    def CurveIdentificationQuery(self):
        """Returns header lines identifying standard sensor and user
        curves loaded in each curve location. Information lines for sensor
        curves 11 thru 31 are available only if the curves actually exist,
        either as a user generated curve or as precision option curve.
        Data returned is defined as follows:
        
            W = Curve number: From 00 to 31.
            X = Curve description: 18 character information line. All 18
                spaces need not be used.
            Y = Temp. coefficient: N = negative coefficient; P = positive
                coefficient.
            Z = Number of points: The number of points for the curve
                (usually 31, but can be up to 99). 
        
        Returns:
        WW,XXXXXXXXXXXXXXXXXX,Y,ZZ,...
        """
        return self.instr.query("CUID?")
    
    def InitiateUserCurve(self, curve):
        """Input:
        CURV AA,SB0CCCCCCCCCCCCCCC,D.DDDDD,EEE.E,...Y.YYYYY,ZZZ.Z*
        
        See manual for details.
        
        Returns: Nothing.
        """
        self.instr.write("CURV"+curve)
        
    def CurveNumberInformationQuery(self):
        """User must provide curve number (00 thru 31) with query.
        The unit will return header line and all point information for
        that curve as follows:
        
            A = Curve number from 11 to 31.
            S = For the Model 330, the first character must be the
                letter 'S.'
            B = Setpoint Limit: 0 = 325 K, 1 = 375 K, 2 = 475 K,
                3 = 800 K, 4 = 999 K.
            0 = Fixed Character - 0 for all curves except 9 for
                thermocouples.
            C = 15-character curve description.
            D = Temp. coefficient: N = negative coefficient;
                P = positive coefficient.
            X = Number of points for the curve (usually 31, but can be up
                to 99).
            Y = Units: voltage or Requiv (see CURV Command) with 1
                character before the decimal and 5 after it (0.00000).
            Z = Temperature with 3 places before the decimal point and
                one after it (000.0).
                
            After sending the CURV? command, values returned include
            temperature coefficient, number of points, and beginning
            and end points. This is normal.
        
        Returns:
        AA,SB0CCCCCCCCCCCCCCC,D,XX,Y.YYYYY,ZZZ.Z...
        """
        return self.instr.query("CURV?")
    
    def EditDataPointInUserCurve(self, curve):
        """Edit or Add A Data Point In User Curve.
        
        Enter the point to be added or edited: XX = curve number from
        11 to 31, Y.YYYYY = voltage, and ZZZ.Z = temperature in kelvin.
        Data points in Curves 00 thru 10 cannot be edited. If the
        Model 330 does not recognize either the units value or the
        temperature value, it assumes you are entering a new point
        and places it in the proper ascending position.
        
        Returns: Nothing.
        """
        self.instr.write("ECUR"+curve)
        
    def CurveBytesFreeQuery(self):
        """Returns the number of curve storage bytes available for
        new curve entry. New curves require at least 100 bytes free.
        A typical 31 point curve requires 176 bytes.
        
        Returns: XXXX (value from 0000 to 3584)
        """
        return self.instr.query("FREE?")
    
    def DeleteUserCurveData(self, curve):
        """Deletes all data stored for the User Curve where XX = user
        curve number 11 thru 31. Curves 00 thru 10 cannot be deleted.
        Repacks the remaining curves within the NOVRAM.
        
        Returns: Nothing.
        """
        self.instr.write("KCUR"+str(curve))
    
    def SoftCalVoltageEntry(self, voltages):
        """Stores the SoftCal voltage values at 4.2 K, 77.32 K, and
        300 K, where AA = Curve number from 11 to 31, X.XXXX = 4.2 K
        voltage, Y.YYYYY = 77.32 K voltage, and Z.ZZZZZ = 300 K voltage.
        
        Returns: Nothing.
        """
        self.instr.write("SCAL"+voltages)
