import visa

class LakeShore218:
    def __init__(self, resource_name):
        self.rm = visa.ResourceManager()
        self.instr = self.rm.open_resource(resource_name)
        self.instr.parity = visa.constants.Parity.odd
        self.instr.data_bits = 7

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        self.instr.close()
        self.rm.close()
    
    #################################################################
    ##########           IEEE-488/SERIAL COMMANDS          ##########
    #################################################################
    
    def ClearInterfaceCommand(self):
        """Clears bits in the Status Byte Register and Standard Event
        Status Register and terminates all pending operations. Clears
        the interface, but not the instrument. See QRST command.
        
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
        """Queries for various Model 218 error conditions and status.
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
        Format: LSCI,MODEL218,aaaaaa,nnnnnn[term]
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
        """Places a “1” in the controller output queue upon completion
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
        """The Model 218 performs a self-test at power-up.
        0 = no errors found, 1 = errors found.
        
        Returns:
        0 or 1. Format: n[term]
        """
        return self.instr.write("*TST?")
    
    def WaitToContinue(self):
        """This command is not supported in the Model 218.

        Returns: Nothing.
        """
        self.instr.write("*WAI")
    
    def ConfigureInputAlarmParameters(self, params):
        """Configures the alarm parameters for an input.
        
        Input:
        ALARM <input>,<off/on>,<source>,<high value>,<low value>,<deadband>,<latch enable>

        Remarks:
            <input> Specifies which input to configure (1-8).
            <off/on> Determines whether the instrument checks the
                     alarm for this input.
            <source> Specifies input data to check. 1 = Kelvin,
                     2 = Celsius, 3 = sensor units, 4 = linear data.
            <high value> Sets the value the source is checked against to
                     activate the high alarm.
            <low value> Sets the value the source is checked against to
                     activate low alarm.
            <deadband> Sets the value that the source must change outside
                     of an alarm condition to deactivate an unlatched
                     alarm.
            <latch enable> Specifies a latched alarm (remains active after
                     alarm condition correction).
        
        Returns: Nothing.
        """
        self.instr.write("ALARM "+params)

    def QueryInputAlarmParameters(self, inp):
        """Returns the alarm parameters of an input. See ALARM
        command for returned parameter descriptions. <input> specifies
        which input to query (1-8).
        
        Returns:
        <off/on>, <source>, <high value>, <low value>, <deadband>, <latch enable>
        """
        return self.instr.query("ALARM? "+str(inp))

    def QueryInputAlarmStatus(self, inp):
        """Returns the alarm status of an input.
        
           <input> Specifies which input to query.
           <high status> Specifies high alarm status. 0 = Unactivated,
               1 = Activated.
           <low status> Specifies low alarm status. 0 = Unactivated,
               1 = Activated.
        
        Returns:
        <high status>, <low status>. Format: n,n[term]
        """
        return self.instr.query("ALARMST? "+str(inp))

    def ConfigureAudibleAlarm(self, onOff):
        """Enables or disables system alarm beeper.
        
        <off/on> disables/enables beeper. 1 = On, 0 = Off
        
        Returns: Nothing.
        """
        self.instr.write("ALMB "+str(onOff))

    def QueryAudibleAlarmParameters(self):
        """Returns system beeper parameters.
        
        Returns:
        <beeper status>. Format: n[term].
        """
        return self.instr.query("ALMB?")
    
    def ClearAlarmStatusAllInputs(self):
        """Resets a latched active alarm after the alarm condition
        has cleared.
        
        Returns: Nothing.
        """
        self.instr.write("ALMRST")    
    
    def ConfigureAnalogOutputParameters(self, params):
        """Configure Analog Output Parameters.
        
        Input:
        ANALOG <output>,<bipolar enable>,<mode>,<input>,<source>,<high value>,<low value>, <manual value>

        Remarks:
            <output> Specifies which analog output to configure (1 or 2).
            <bipolar enable> Specifies analog output: 0 = positive only,
                or 1 = bipolar.
            <mode> Specifies data the analog output monitors: 0 = off,
                1 = input, 2 = manual.
            <input> Specifies which input to monitor if <mode> = 1 (1-8).
            <source> Specifies input data. 1 = Kelvin, 2 = Celsius,
                3 = sensor units, 4 = linear equation.
            <high value> If <mode> = 1, this parameter represents the data
                at which the analog output reaches +100% output.
            <low value> If <mode> = 1, this parameter represents the data
                at which the analog output reaches -100% output if bipolar,
                or 0% output if positive only.
            <manual value> If <mode> = 2, this parameter is the output of
                the analog output.
        
        Returns: Nothing.
        """
        self.instr.write("ANALOG "+params)        
    
    def QueryAnalogOutputParameters(self, output):
        """Query Analog Output Parameters.
        
        See the ANALOG command for parameter descriptions.
        
        Returns:
        <bipolar enable>, <mode>, <input>, <source>, <high value>, <low value>, <manual value>
        Format: n,n,n,n,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn[term].
        """
        return self.instr.query("ANALOG? "+str(output))        
    
    def QueryAnalogOutputData(self, output):
        """Returns the percentage of output. 
        <output> specifies analog output to query.
        
        Returns:
        <analog output>. Format: +/-nn.nnn[term]
        """
        return self.instr.query("AOUT? "+str(output))  
    
    def ConfigureSerialInterfaceBaudRate(self, bps):
        """Configures to serial interface baud rate.
        
        <bps> specifies bits per second (bps) rate.
            0 = 300,
            1 = 1200,
            2 = 9600.
        
        Returns: Nothing.
        """
        self.instr.write("BAUD "+str(bps))          
    
    def QuerySerialInterfaceBaudRate(self):
        """Returns serial interface baud rate. See BAUD command
        for parameter descriptions.
        
        Returns:
        <bps>. Format: n[term].
        """
        return self.instr.query("BAUD?")

    def QueryCelsiusReading(self, inputs=0):
        """Query Celsius Reading for a single Input or All Inputs
        
        Returns the Celsius reading for a single input or all inputs.
        
        <input> specifies which input(s) to query.
        
            0 = all inputs,
            1-8 = individual input.
        
        NOTE: Use 0 (all inputs) when reading two or more inputs at the
        maximum update of 16 rdgs/sec.

        Returns:
        <Celsius value>. Format: +/-nn.nnn[term].
        
        Or if all inputs are queried:
        <Input 1 Celsius Value>,<Input 2 Celsius Value>,<Input 3 Celsius Value>,<Input 4 Celsius Value>,<Input 5 Celsius Value>,<Input 6 Celsius Value>,<Input 7 Celsius Value>,<Input 8 Celsius Value>.
        Format: +/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn
        """
        return self.instr.query("CRDG? "+str(inputs))

    def DeleteUserCurve(self, curve):
        """Deletes a user curve. <curve> specifies which curve to delete
        (21-28) for inputs 1-8.
        
        Returns: Nothing.
        """
        self.instr.write("CRVDEL "+str(curve))   
        
    def ConfigureCurveHeader(self, params):
        """Configure Curve Header.
        
        Input:
        CRVHDR <curve>, <name>, <SN>, <format>, <limit value>, <coefficient>
        
        Remarks: <curve> Specifies which curve to configure (21-28) for inputs 1-8.
            <name> Specifies curve name. Limited to 15 characters.
            <SN> Specifies curve serial number. Limited to 10 characters.
            <format> Specifies curve data format. 2 = V/K, 3 = Ohm/K,
                4 = log Ohm/K
            <limit value> Specifies curve temperature limit in Kelvin.
            <coefficient> Specifies curve temperature coefficient.
                1 = negative, 2 = positive
        
        Returns: Nothing.
        """
        self.instr.write("CRVHDR "+params)   
        
    def QueryCurveHeader(self, curve):
        """Returns a standard or user curve header. See CRVHDR command
        for parameter descriptions. <curve> specifies which curve to query.
        1-5 = Standard Diode Curves, 6 -9 = Standard Platinum Curves,
        21-28 = User Curves. NOTE: Curve Locations 10-20 not used.

        Returns:
        <name>, <SN>, <format>, <limit value>, <coefficient>
        Format: aaaaaaaaaaaaaaa,aaaaaaaaaa,n,nnn.nnn,n[term]
        """
        return self.instr.query("CRVHDR? "+str(curve))
        
    def ConfigureCurveDataPoint(self, params):
        """Configures a user curve data point.
        
        Input:
        CRVPT <curve>, <index>, <units value>, <temp value>

        <curve> Specifies which curve to configure (21-28) for inputs 1-8.
        <index> Specifies the points index in the curve (1 - 200).
        <units value> Specifies sensor units for this point to 6 digits.
        <temp value> Specifies corresponding temperature in Kelvin for
            this point to 6 digits.
        
        Returns: Nothing.
        """
        self.instr.write("CRVPT "+params)   

    def QueryCurveDataPoint(self, curve, index):
        """Returns a standard or user curve data point.
        
        See CRVPT command for parameter descriptions.
        
        <curve> Specifies which curve to query. 1-5 = Standard Diode Curves,
            6-9 = Standard Platinum Curves, 21-28 = User Curves.
            NOTE: Curve locations 10-20 not used.
        <index> Specifies the points index in the curve (1 - 200).

        Returns:
        <units value>, <temp value>. Format: +nnn.nnn,+nnn.nnn[term]
        """
        return self.instr.query("CRVPT? "+str(curve)+','+str(index))
                         
    def ConfigureDateTime(self, datetime):
        """Configures date and time using 24-hour format.
        
        Input:
        DATETIME <MM>, <DD>, <YY>, <HH>, <mm>, <SS>.

        Remarks: 
            <MM> Specifies month. Valid entries are: 1 - 12.
            <DD> Specifies day. Valid entries are 1 - 31.
            <YY> Specifies year. Valid entries are: 00 - 99.
            <HH> Specifies hour. Valid entries are: 0 - 23.
            <mm> Specifies minutes. Valid entries are: 0 - 59.
            <SS> Specifies seconds. Valid entries are: 0 - 59.
        
        Returns: Nothing.
        """
        self.instr.write("DATETIME "+datetime)

    def QueryDateTime(self):
        """Returns date and time. See the DATETIME command for
        parameter descriptions.

        Returns:
        <MM>, <DD>, <YY>, <HH>, <mm>, <SS>.
        Format: nn,nn,nn,nn,nn,nn,[term]
        """
        return self.instr.query("DATETIME?")
                         
    def SetFactoryDefaults(self):
        """Sets all configuration values to factory defaults and resets
        the instrument. Does not clear user curves or instrument
        calibration.
        
        Returns: Nothing.
        """
        # The 99 is required to prevent accidentally setting
        # the unit to defaults.
        self.instr.write("DFLT 99")
                         
    def ConfigureDisplayParameters(self, params):
        """Configures the display parameters.
        
        Input: DSPFLD <location>, <input>, <source>

        <location> Specifies display location to configure (1 - 8).
        <input> Specifies input to display in the display location
            (0 - 8). (0=none).
        <source> Specifies input data to display. 1 = Kelvin,
            2 = Celsius, 3 = sensor units, 4 = linear data,
            5 = minimum data, 6 = maximum data.

        Returns: Nothing.
        """
        self.instr.write("DISPFLD")
        
    def QueryDisplayedField(self):
        """Returns the parameters for a displayed field.
        See DISPFLD command for returned parameter descriptions.
        <location> specifies display location to query (1 - 8).

        Returns:
        <input>, <source>. Format: n,n,n[term]
        """
        return self.instr.query("DISPFLD?")
                         
    def ConfigureInputFilterParameters(self, params):
        """Configure Input Filter Parameters.
        
        Input:
        FILTER <input>, <off/on >, <points>, <window>

        Remarks:
            <input> Specifies input to configure (1-8).
            <off/on> Specifies whether the filter function is off or on.
                0 = Off, 1 = On.
            <points> Specifies how many data points the filtering function
                uses (2-64).
            <window> Specifies what percent of full scale reading limits
                the filtering function (1-10). Reading changes greater
                than this percentage reset the filter.

        Returns: Nothing.
        """
        self.instr.write("FILTER "+params)
        
    def QueryInputFilterParameters(self, inp):
        """Returns input filter configuration.
        
        See FILTER command for returned parameter descriptions.
        
        <input> specifies which input to query (1-8).

        Returns:
        <off/on >, <points>, <window>. Format: n,nn,nn[term]
        """
        return self.instr.query("FILTER? "+str(inp))
                         
    def ConfigureGPIBInterfaceParameters(self, params):
        """Configures parameters of the IEEE interface.
        
        Input:
        IEEE[<terminator>, <EOI enable>, <address>
        
        Remarks:
            <terminator> Specifies the terminator. 0 = <CR><LF>,
                1 = <LF><CR>, 2 = <LF>, 3 = no terminator.
            <EOI enable> Disables/enables the EOI mode. 0 = Enabled,
                1 = Disabled.
        <address> Specifies the IEEE address.

        Returns: Nothing.
        """
        self.instr.write("IEEE "+params)
                         
    def QueryGPIBInterfaceParameters(self):
        """Returns IEEE interface parameters.
        
        See IEEE command for returned parameter descriptions.

        Returns:
        <terminator>, <EOI enable>, <address>. Format: n,n,nn[term]
        """
        return self.instr.query("IEEE?")
                         
    def ConfigureInputCurveNumber(self, params):
        """Specifies the curve an input uses for temperature conversion.
        
        Input: INCRV <input>, <curve number>

        Remarks:
            <input> Specifies which input to configure (1-8).
            <curve number> Specifies which curve the input uses.
                0 = none, 1-5 = Standard Diode Curves, 6-9 = Standard
                Platinum Curves, 21-28 = User curves.
                Note: Curve locations 10-20 not used.

        Returns: Nothing.
        """
        self.instr.write("INCRV "+params)

    def QueryInputCurveNumber(self, inp):
        """Returns the input curve number.
        
        See the INCRV command for parameter descriptions.
        
        <input> Specifies which input to query (1-8).
        <curve number> Specifies which curve the input uses. 0 = none,
            1 - 5 = Standard Diode Curves, 6-9 = Standard Platinum Curves,
            21-28 = User Curves. Note: Curve locations 10-20 not used.

        Returns:
        <curve number>. Format: nn[term]
        """
        return self.instr.query("INCRV? "+str(inp))
                         
    def ConfigureInputControlParameter(self, params):
        """Turns selected input on or off.

        Input:
        INPUT <input>, <off/on>
        
        Remarks: 
            <input> Specifies which input to configure(1-8).
            <off/on> Disables/Enables input. 0 = Off, 1 = On.

        Returns: Nothing.
        """
        self.instr.write("INPUT "+params)
                         
    def QueryInputControlParameter(self, inp):
        """Returns selected input status.
        
        <input> specifies which input to query (1-8).

        Returns:
        <off/on>. Format: n[term]
        """
        return self.instr.query("INPUT? "+str(inp))
                         
    def ConfigureInputTypeParameters(self, params):
        """Configures input type parameters for a group of inputs.
        Input:
        INTYPE <input group>, <sensor type>

        Remarks:
            <input group> Specifies input group to configure.
                A = inputs 1-4, B = inputs 5-8.
            <sensor type> Specifies input sensor type. Valid entries:
                0 = 2.5V Diode 2 = 250? Platinum 4 = 5k? Platinum
                1 = 7.5V Diode 3 = 500? Platinum 5 = Cernox

        Returns: Nothing.
        """
        self.instr.write("INTYPE "+params)
                         
    def QueryInputTypeParameters(self, input_group):
        """Returns input type parameters.
        
        <input group> Specifies input group to query.
            A = inputs 1-4, B = inputs 5-8.
        <sensor type> Specifies input sensor type. Valid entries:
            0 = 2.5V Diode 2 = 250? Platinum 4 = 5k? Platinum
            1 = 7.5V Diode 3 = 500? Platinum 5 = Cernox

        Returns:
        <sensor type>. Format: n[term]
        """
        return self.instr.query("INTYPE? "+str(input_group))
                         
    def QueryKeypadStatus(self):
        """Returns keypad status since the last KEYST?.
        
        1 = key pressed, 0 = no key pressed.
        
        KEYST? returns 1 after initial power-up.

        Returns:
        <keypad status>. Format: n[term]
        """
        return self.instr.query("KEYST?")
                         
    def QueryKelvinReading(self, inputs=0):
        """Returns the Kelvin reading for a single input or all inputs.
        
        <input> specifies which input(s) to query. 0 = all inputs,
        1-8 = individual input. NOTE: Use 0 (all inputs) when reading two
        or more inputs at the maximum update rate of 16 rdg/s.

        Returns:
        <Kelvin value>. Format: +nn.nnn[term]

        Or if all inputs are queried:
        <Input 1 Kelvin Value>,<Input 2 Kelvin Value>,<Input 3 Kelvin Value>,<Input 4 Kelvin Value>,<Input 5 Kelvin Value>,<Input 6 Kelvin Value>,<Input 7 Kelvin Value>,<Input 8 Kelvin Value>. Format: +nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn
        """
        return self.instr.query("KRDG? "+str(inputs))
                         
    def ConfigureInputLinearEquationParameters(self, params):
        """Configures the linear equation for an input.
        
        Input:
        LINEAR <input>, <varM value>, <X source>, <varB value>

        Remarks:
            <input> Specifies input to configure (1-8).
            <varM value> Specifies a value for m in the equation.
            <X source > Specifies input data. 1 = Kelvin, 2 = Celsius,
                3 = sensor units.
            <varB value> Specifies a value for b in the equation.
            
        Returns: Nothing.
        """
        self.instr.write("LINEAR "+params)
                         
    def QueryInputLinearEquationParameters(self, inp):
        """Returns input linear equation configuration.
        
        See LINEAR command for returned parameter descriptions.
        
        <input> specifies input to query (1-8).

        Returns:
        <varM value>,<X source>,<varB value>.
        Format: +/-nn.nnn,n,+/-nn.nnn
        """
        return self.instr.query("LINEAR? "+str(inp))
                         
    def ConfigureLockCode(self, params):
        """Configures keypad lock-out and lock-out code.
        
        Input:
        LOCK <off/on>, <code>
        
        Remarks: 
            <off/on> Disables/enables the keypad lock-out.
            <code> Specifies lock-out code. 000 - 999
            
        Returns: Nothing.
        """
        self.instr.write("LOCK "+params)
                         
    def QueryLockCode(self):
        """Returns lock-out status and lock-out code.
        
        See LOCK command for parameter descriptions.

        Returns:
        <off/on>, <code>. Format: n,nnn[term]
        """
        return self.instr.query("LOCK?")
                         
    def TurnsLoggingOnOff(self, onOff):
        """Turns logging on and off.
        
        <off/on> 0 = Off, 1 = On.
            
        Returns: Nothing.
        """
        self.instr.write("LOG "+str(onOff))
                         
    def QueryLoggingStatus(self):
        """Returns logging status.
        
        See LOG command for parameter descriptions.
        
        Returns:
        <off/on>. Format: n[term]
        """
        return self.instr.query("LOG?")
                         
    def QueryLastDataLogRecordNumber(self):
        """Returns number of last data log record stored.
            
        Returns:
        <last record number>. Format: nnnn[term]
        """
        self.instr.query("LOGNUM?")
                         
    def ConfigureLogRecords(self, params):
        """Configures log records.
        
        Input:
        LOGREAD <reading number>, <input>, <source>
        
        Remarks:
            <reading number> The individual reading number (1-8) within
                a log record to configure.
            <input> The input number to log (1-8).
            <source> Specifies data source to log. 1 = Kelvin, 2 = Celsius,
                3 = sensor units, 4 = linear data
            
        Returns: Nothing.
        """
        self.instr.write("LOGREAD "+params)
                         
    def QueryLogRecordParameters(self, num):
        """Returns log record parameters.
        
        See LOGREAD command description of returned parameters.
        
        <reading number> specifies an individual reading number (1-8)
        within a log record to query.
            
        Returns:
        <input>, <source>. Format: n,n[term]
        """
        return self.instr.query("LOGREAD? "+str(num))
                         
    def ConfigureLoggingParameters(self, params):
        """Configures logging parameters.
        
        Input:
        LOGSET <mode>, <overwrite>, <start>, <period>, <readings>
        
        Remarks:
            <mode> Specifies logging mode. 0 = Off, 1 = Log Continuous,
            2 = Log event, 3 = Print Continuous, 4 = Print Event.
            <overwrite> Specifies overwrite mode. 0 = Do not overwrite
                data, 1 = overwrite data.
            <start> Specifies start mode. 0 = Clear, 1 = Continue.
            <period> Specifies period in seconds (1-3600).
                If mode is Print Continuous, minimum period is 10.
            <readings> Specifies number of readings per record (1-8).
            
        Returns: Nothing.
        """
        self.instr.write("LOGSET "+params)
                         
    def QueryLoggingParameters(self):
        """Returns logging parameters.
        
        See LOGSET command description of returned parameters
            
        Returns:
        <mode>, <overwrite>, <start>, <period>, <readings>.
        Format: n,n,n,nnnn,n[term]
        """
        return self.instr.query("LOGSET?")
                         
    def QueryLoggedDataRecord(self, params):
        """Returns a single reading from a logged data record.
        
        Input:
        LOGVIEW? <record number>, <reading number>

        Remarks:
            <date> Date reading was recorded.
            <time> Time reading was recorded.
            <reading> Reading logged.
            <status> Represents the sum of the bit weighting of the
                reading status flag bits.
                    Bit Bit_Weighting Status Indicator
                    0 1 Low Alarm
                    1 2 High Alarm
                    2 4 Temperature Over or Under Range
                    3 8 Sensor Over or Under Range
            <source> Returns data source recorded. 1 = Kelvin, 2 = Celsius,
                3 = sensor units, 4 = linear data.

        Returns:
        <date>,<time>,<reading>,<status>,<source>
        Format: nn/nn/nn,nn:nn:nn,+/-nn.nnn,nn,n[term]
        """
        return self.instr.query("LOGVIEW? "+params)
                         
    def QueryLinearEquationData(self, inputs=0):
        """Returns the linear equation data for an input.
        
        <input> specifies which input to query. 0 = all inputs,
        1-8 = individual input. NOTE: Use 0 (all inputs) when reading
        two or more inputs at the maximum update rate of 16 rdg/s.

        Returns:
        <Linear value>. Format: +/-nn.nnn[term]
        
        Or if all inputs are queried:
        <Input 1 Linear Value>,<Input 2 Linear Value>,<Input 3 Linear Value>,<Input 4 Linear Value>,<Input 5 Linear Value>,<Input 6 Linear Value>,<Input 7 Linear Value>,<Input 8 Linear Value>. Format: +/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn,+/-nn.nnn+/-nn.nnn,+/-nn.nnn
        """
        return self.instr.query("LRDG? "+str(inputs))
                         
    def ConfigureMinMaxInputFunctionParameters(self, params):
        """Configures the minimum and maximum input functions.
        
        Input:
        MNMX <input>, <source>
        
        Remarks:
            <input> Specifies input to configure (1-8).
            <source> Specifies input data to process through max/min.
                1 = Kelvin, 2 = Celsius, 3 = sensor units, 4 = linear data.
            
        Returns: Nothing.
        """
        self.instr.write("MNMX "+params)
                         
    def QueryMinMaxInputFunctionParameters(self, inp):
        """Returns an input min/max configuration.
        
        <input> Specifies input to query (1-8).
        <source> Specifies input data to process through max/min.
            1 = Kelvin, 2 = Celsius, 3 = sensor units, 4 = linear data.

        Returns:
        <source>. Format: n[term]
        """
        self.instr.query("MNMX? "+str(inp))
                         
    def QueryMinMaxInputFunctionParameters(self, inp):
        """Returns the minimum and maximum input data.
        
        <input> specifies which input to query.
        
        Returns:
        <min value>,<max value>. Format: +/-nn.nnn,+/-nn.nnn[term]
        """
        return self.instr.query("MNMXRDG? "+str(inp))
                         
    def ResetsMinMaxFunctionAllInputs(self):
        """Resets the minimum and maximum data for all inputs.
            
        Returns: Nothing.
        """
        self.instr.write("MNMXRST")
                         
    def Mode(self, mode):
        """Configures the remote interface mode.
        
        <mode> specifies which mode to operate.
            0 = local,
            1 = remote,
            2 = remote with local lockout.
        
        Returns: Nothing.
        """
        self.instr.write("MODE "+str(mode))
        
    def ModeQuery(self):
        """Returns the remote interface mode.
        
            0 = local,
            1 = remote,
            2 = remote with local lockout
        Returns:
        
        <mode>. Format: n[term]
        """
        return self.instr.query("MODE?")
                         
    def QueryInputStatus(self, inp):
        """The integer returned represents the sum of the bit
        weighting of the input status flag bits.
        
        <input> specifies which input to query.
        
        Returns:
        <reading bit weighting>. Format: nnn[term]
        """
        return self.instr.query("RDGST? "+str(inp))
                         
    def ConfigureRelayControlParameters(self, params):
        """Configures relay control.
        
        Input:
        RELAY <relay number>, <mode>, <input alarm>, <alarm type>

        Remarks:
            <relay number> Specifies which relay to configure (1- 8).
            <mode> Specifies relay mode. 0 = Off, 1 = On, 2 = Alarms
            <input alarm> Specifies which input alarm activates the relay
                when the relay is in alarm mode (1- 8).
            <alarm type> Specifies the input alarm type that activates the
                relay when the relay is in alarm mode.
                0 = Low alarm, 1 = High Alarm, 2 = Both Alarms.
            
        Returns: Nothing.
        """
        self.instr.write("RELAY "+params)
                         
    def QueryRelayControlParameters(self, relay_number):
        """Returns relay control parameters.
        
        See the RELAY command for returned parameter descriptions.
        
        <relay number> specifies which relay to query.
        
        Returns:
        <mode>, <input>, <alarm type>
        """
        return self.instr.query("RELAY? "+str(relay_number))
                         
    def QueryRelayStatus(self):
        """The integer returned represents the sum of the bit weighting
        of the relay status.
        
        Bit Bit_Weighting Active_Relay
        0 1 Relay_1
        1 2 Relay_2
        2 4 Relay_3
        3 8 Relay_4
        4 16 Relay_5
        5 32 Relay_6
        6 64 Relay_7
        7 128 Relay_8
        
        Returns:
        <relay status bit weighting>. Format: nnn[term]
        """
        return self.instr.query("RELAYST?")
                         
    def GenerateSoftCalCurve(self, params):
        """
        
        Input:
        SCAL <std>, <dest>, <SN>, <T1 value>, <U1 value>, <T2 value>, <U2 value>, <T3 value>, <U3 value>

        Remarks:
            <std> Specifies the standard curve to generate a SoftCal™ 
                rom (1,6,7).
            <dest> Specifies the user curve to store the SoftCal™ curve
                (21 – 28).
            <SN> Specifies the curve serial number. Limited to 10
                characters.
            <T1 value> Specifies first temperature point.
            <U1 value> Specifies first sensor units point.
            <T2 value> Specifies second temperature point.
            <U2 value> Specifies second sensor units point.
            <T3 value> Specifies third temperature point.
            <U3 value> Specifies third sensor units point.
            
        Returns: Nothing.
        """
        self.instr.write("SCAL "+params)
                         
    def QuerySensorUnitsReading(self, inputs=0):
        """Returns the Sensor Units reading for a single input or all
        inputs.
        
        <input> Specifies which input(s) to query. 0 = all inputs,
        1-8 = individual input. NOTE: Use 0 (all inputs) when reading
        two or more inputs at the maximum update rate of 16 rdg/s.
        
        Returns:
        <sensor units value>. Format: +nn.nnn[term]
        
        Or if all units are queried:
        <Input 1 Sensor Units Value>,<Input 2 Sensor Units Value>,<Input 3 Sensor Units Value>,<Input 4 Sensor Units Value>,<Input 5 Sensor Units Value>,<Input 6 Sensor Units Value>,<Input 7 Sensor Units Value>,<Input 8 Sensor Units Value>
        Format: +nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn,+nn.nnn
        """
        return self.instr.query("SRDG?")
