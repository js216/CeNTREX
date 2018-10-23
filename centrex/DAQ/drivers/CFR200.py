import visa

class CFR200:
    def __init__(self, rm, resource_name):
        self.rm = rm
        self.instr = self.rm.open_resource(resource_name)
        self.instr.parity = visa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.write_termination = '\r\n'
        self.instr.read_termination = None

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        self.instr.close()
        
    def query(self, cmd):
        self.instr.write(cmd)
        # the answer consists of "CRLF" followed by 15 characters
        # (see manual, page 51)
        return self.instr.read_bytes(17)[2:].decode('ASCII')
    
    #################################################################
    ##########  Convenience functions                      ##########
    #################################################################
    
    def dump_config(self):
        """Return all the values that can be read from the device."""
        return [
            self.ReadSoftwareReview(),
            self.ReadDateOfSoftwareReview(),
            self.ReadCoolingGroupTempC(),
            self.ReadCoolingGroupTempF(),
            self.ReadCurrentConfig(),
            self.ReadTimeCounter(),
            self.ReadShutterState(),
            self.ReadShutterAtRun(),
            self.ReadRackType(),
            self.ReadCapacitorType(),
            self.ReadLaserType(),
            self.ReadFlashlampVoltage(),
            self.ReadFlashlampTriggerMode(),
            self.ReadFlashlampRepRate(),
            self.ReadFlashlampShotCounter(),
            self.ReadFlashlampUsersShotCounter(),
            self.ReadQSMode(),
            self.ReadQSAutoFn(),
            self.ReadQSNumPulsesBurstMode(),
            self.ReadTurnQSOnOff(),
            self.ReadQSCount(),
            self.ReadQSUsersCount(),
            self.ReadQSFlashlampDelay(),
            self.ReadDelayQS1QS2(),
            self.ReadVariableQSSynchroOut(),
            self.TestFlashlampSafetyInterlock(),
            self.TestQSSafetyInterlock(),
            self.ReadTimeoutStatus(),
            self.ReadHarmonicGeneratorToTemp(),
            self.ReadSimmerCounterOrder(),
            self.ReadFiringCounterOrder(),
            self.ReadQSCounterOrder(),
            self.ReadSimmerCounter(),
            self.ReadRepRateCounter(),
            self.ReadSimmerCounter(),
        ]
    
    #################################################################
    ##########  Configuration parameters (Reading)         ##########
    #################################################################
    
    def ReadSoftwareReview(self):
        """Software review used.
        
        Returns: XXXXXXX  -.--
        """
        return self.query('X')
    
    def ReadDateOfSoftwareReview(self):
        """Date of Software review (date/month/year).
        
        Returns: --/--/--       
        """
        return self.query('DAT')
        
    def ReadCoolingGroupTempC(self):
        """Reads cooling group Temp ( C).
        
        Returns: temp. CG -- d  
        """
        return self.query('CG')
    
    def ReadCoolingGroupTempF(self):
        """Reads cooling group Temp ( F).
        
        Returns: temp. CG --- F 
        """
        return self.query('CGF')
    
    def ReadDispType(self):
        """Reads type of display ( C or  F).
        
        Returns: option TP  :  -
        """
        return self.query('NTP')
    
    def ReadCurrentConfig(self):
        """Read the current configuration.
        
        Returns: configuration -
        """
        return self.query('CFF')
    
    def ReadTimeCounter(self):
        """Time counter (When switch ON hhhh= number hours and mm=minutes).
        
        Returns: ct time hhhh:mm
        """
        return self.query('T')
    
    def ReadShutterState(self):
        """Reads shutter state.
        
        Returns: shutter closed 
                 shutter opened 
        """
        return self.query('R')
    
    def ReadShutterAtRun(self):
        """Reads open or close the shutter at run.
        
        Returns: shutt. at run -
        """
        return self.query('ROF')
    
    def ReadRackType(self):
        """The type of rack.
        
        Returns: option MPS :  -
        """
        return self.query('NPS')
    
    def ReadCapacitorType(self):
        """The type of capacitor.
        
        Returns: option CAP :  - 
        """
        return self.query('NCA')
    
    def ReadLaserType(self):
        """Read the type of laser (15 = version CFR).
        
        Returns: option B2K : 15
        """
        return self.query('NOP')
    
    #################################################################
    ##########  Configuration parameters (Programming)     ##########
    #################################################################
    
    def LoadNewConfig(self, config):
        """Loading a new configuration.
        
        Valid range: 1 -- 4
        
        Returns: configuration 1
        """
        return self.query('CFG'+str(config))
    
    def SaveCurrentConfig(self, config):
        """Saving the current configuration.
        
        Valid range: 1 -- 4
        
        Returns: Save config.  2
        """
        return self.query('SAV'+str(config))
    
    def SetTempDispF(self, config):
        """Sets temperature display in  F.
        
        Valid range: 0 -- 1 (0 =  C, 1 =  F)
        
        Returns: option TP  :  1
        """
        return self.query('NTP'+str(config))
    
    def SetShutterOpen(self, config):
        """Sets opened or closed the shutter.
        
        Valid range: 0 -- 1
        
        Returns: shutter opened 
        """
        return self.query('R'+str(config))
    
    def OpenShutterAtRun(self, config):
        """Open or close the shutter at run.
        
        Valid range: 0 - 1 (1 = Open the shutter at run) 
        
        Returns: shutt. at run 1
        """
        return self.query('ROF'+str(config))
 
    def LaserStatus(self):
        """Status of laser.
        
        See manual (page 52) for interpretation of return value.

        Returns: I a F b S c Q d 
        """
        return self.query('WOR')
    
    def LampQSStatus(self):
        """Reads the status of the lamp & QS operating mode.
        
        See manual for details (no idea which part of it!).
        """
        return self.query('')
    
    #################################################################
    ##########  Flashlamp parameters (Reading)             ##########
    #################################################################    
    
    def ReadFlashlampVoltage(self):
        """Flashlamp voltage (V).
        
        Returns: voltage  ---- V
        """
        return self.query('V')
    
    def ReadFlashlampTriggerMode(self):
        """Trigger Flashlamp mode.
        
        Returns: LP synch :  -  
        """
        return self.query('LPM')
    
    def ReadFlashlampRepRate(self):
        """Pre-set repetition rate (Hz).
        
        Returns: freq.  --.-- Hz
        """
        return self.query('F')
    
    def ReadFlashlampShotCounter(self):
        """Lamp shot counter (9 digits).
        
        Returns: ct LP ---------
        """
        return self.query('C')
    
    def ReadFlashlampUsersShotCounter(self):
        """Lamp User's shot counter (9 digits)
        
        Returns: cu LP ---------
        """
        return self.query('UC')
    
    #################################################################
    ##########  Flashlamp parameters (Programming)         ##########
    #################################################################
    
    def SetFlashlampTriggerMode(self, config):
        """Sets trigger Flashlamp mode.
        
        Valid range: 0 -- 1 (Internal trigger = 0 or External trigger = 1) 
        
        Returns: LP synch :  0  
        """
        return self.query('LPM'+str(config))

    def SetFlashlampVoltage(self, config):
        """Flashlamp voltage (V).
        
        Valid range: 500 -- 1800 & Vmin < V < Vmax (factory set limits)
        
        Returns: voltage  0920 V
        """
        return self.query('V'+str(config))
    
    def SetFlashlampRepRate(self, config):
        """Sets repetition rate (Hz).
        
        Valid range: 1 -- 9999 
        
        Returns: freq.  12.25 Hz
        """
        return self.query('F'+str(config))
    
    def ResetUsersLampShotCounter(self):
        """Reset Lamp User's shot counter.
        
        Valid range: 1 -- 9999 
        
        Returns: cu LP 000000000
        """
        return self.query('UC0')
    
    #################################################################
    ##########  Flashlamp activation/deactivation          ##########
    #################################################################
    
    def ActivateFlashlampAutoFire(self):
        """Activates automatic fire of lamp in the preselected
        operating mode.
        
        See manual (page 53) for details.
        """
        return self.query('A')
    
    def StopFlashlampAutoFire(self):
        """Stops automatic internal or external lamp firing.
        
        See manual (page 53) for details.
        """
        return self.query('S')
    
    def SetFlashlampSimmer(self):
        """Set the lamp on Simmer in the preselected operating mode.
        
        See manual (page 53) for details.
        """
        return self.query('S')
    
    #################################################################
    ##########  Q-switch parameters (Reading)              ##########
    #################################################################    
    
    def ReadQSMode(self):
        """Read Q-S mode.
        
        Returns: QS mode  :   -  
        """
        return self.query('QSM')
    
    def ReadQSAutoFn(self):
        """Read Q-S F/n in auto mode.
        
        Returns: cycle rate F/-- 
        """
        return self.query('QSF')
    
    def ReadQSNumPulsesBurstMode(self):
        """Read Q-S the number of pulses in burst mode.
        
        Returns: burst QS    ---
        """
        return self.query('QSP')
    
    def ReadTurnQSOnOff(self):
        """Turns Q-Switch ON or OFF.
        
        Returns: QS at run     -
        """
        return self.query('QOF')
    
    def ReadQSCount(self):
        """Q-Switch shot counter (9 digits).
        
        Returns: ct QS --------- 
        """
        return self.query('CQ')
    
    def ReadQSUsersCount(self):
        """Q-Switch User's shot counter (9 digits).
        
        Returns: cu QS --------- 
        """
        return self.query('UCQ')
    
    def ReadQSFlashlampDelay(self):
        """Delay between flashlamp & Q-S.
        
        Returns: delay    --- uS
        """
        return self.query('W')
    
    def ReadDelayQS1QS2(self):
        """Delay between Q-S1 & Q-S2. Only option double pulse.
        
        Returns: QS1-QS2  --- uS
        """
        return self.query('WD')
    
    def ReadVariableQSSynchroOut(self):
        """Variable QS synchro out (ns).
        
        Valid range: -500 to +500.
        
        Returns: var. QS +/- --- nS
        """
        return self.query('VQ')
    
    #################################################################
    ##########  Q-switch parameters (Reading)              ##########
    #################################################################  
    
    def SetQSBurstMode(self, config):
        """Sets Q-S mode burst. Auto = 0, Burst = 1 and Ext = 2.
        
        Returns: QS mode  :   1  
        """
        return self.query('QSM'+str(config))
    
    def SetQSF10(self, config):
        """Set Q-S F/10.
 
        Valid range: 1 to 99.
        
        Returns: cycle rate F/10
        """
        return self.query('QSF'+str(config))
    
    def SetQS50Bursts(self, config):
        """Sets Q-S 50 bursts.
        
        Valid range: 1 to 999
        
        Returns: burst QS    050
        """
        return self.query('QSP'+str(config))
    
    def TurnQSOn(self, config):
        """Turns Q-Switch ON.
        
        Valid range: 0 -- 1 (0=OFF, 1=ON)
        
        Returns: QS at run     1
        """
        return self.query('QOF'+str(config))
    
    def ResetQSUserCounter(self):
        """Reset Q-Switch User's shot counter.

        Returns: cu QS 000000000
        """
        return self.query('UCQ0')
    
    def SetQSFlashlampDelay(self, config):
        """Sets QS-Flash delay in us.
        
        Valid range: 80us to 999 us & Wmin < W< Wmax (factory set limits) 
        
        Returns: delay    225 uS
        """
        return self.query('W'+str(config))
    
    def SetQS1QS2Delay(self, config):
        """Sets delay between Q-S1 & Q-S2.
        
        Valid range : 30us to 250 us
        
        For one pulse sets value < 30.
        
        Returns: QS1-QS2  100 uS
        """
        return self.query('WD'+str(config))
    
    def SetVariableQSSynchroOut(self, config):
        """Sets Variable QS synchro out (ns).

        Valid range : -500ns to +500ns
        
        Returns: var. QS +250 nS
        """
        return self.query('VQ+'+str(config))
    
    def ReadMinDelayQS(self):
        """Below limit delay QS.
        
        Returns: dly QS m --- uS 
        """
        return self.query('WMN')
    
    def ReadMaxDelayQS(self):
        """Above limit delay QS.
        
        Returns: dly QS M --- uS 
        """
        return self.query('WMX')
    
    def ReadNumPulsesWaitBeforeQS(self):
        """Number of pulses to wait after starting the lamp before
        enabling the q-switch.
        
        Returns: QS wait :  ---
        """
        return self.query('QSW')
    
    def ReadRamp(self):
        """Ramp in number of pulse Q-S.
        
        Valid range: 0 ^ 99 
        
        Returns: QS ramp :  ---
        """
        return self.query('QSR')
    
    def ReadRampStep(self):
        """Step of ramp Q-S in uS.

        Returns: tp QS min --d 
        """
        return self.query('TQN')
    
    def MinTempQS(self):
        """Low limit temperature ( C) for QS.

        Returns: QS step : --uS 
        """
        return self.query('QSS')
    
    #################################################################
    ##########  Q-switch activation/deactivation           ##########
    #################################################################
    
    def StartQS(self):
        """Start Q-Switch laser emission in the preselected operating mode.
        
        See manual (page 54) for details.
        """
        return self.query('PQ')
    
    def StopQS(self):
        """Stop Q-Switch laser emission.
        
        See manual (page 54) for details.
        """
        return self.query('SQ')
    
    def SinglePulseQS(self):
        """Single pulse Q-S laser emission in the preselected
        operating mode.
        
        See manual (page 55) for details.
        """
        return self.query('OQ')
    
    #################################################################
    ##########  Safety devices                             ##########
    #################################################################
    
    def TestFlashlampSafetyInterlock(self):
        """Test flashlamp safety interlock.
        
        See manual (page 55) for details.
        """
        return self.query('IF')
    
    def TestQSSafetyInterlock(self):
        """Test Q-Switch safety devices.
        
        See manual (page 55) for details.
        """
        return self.query('IQ')
    
    #################################################################
    ##########  Function time out (reading)                ##########
    #################################################################
    
    def ReadTimeoutStatus(self):
        """Time out status.
        
        Returns: time out      -
        """
        return self.query('L')
    
    def ReadHarmonicGeneratorToTemp(self):
        """Harmonic Generator to temp.
        
        a=1 ready, a=1 not ready temp to low
        
        Returns: IHG           a
        """
        return self.query('IHG')
    
    def ReadSimmerCounterOrder(self):
        """Simmer counter order.
        
        Returns: con SIM = --:--
        """
        return self.query('CLS')
    
    def ReadFiringCounterOrder(self):
        """Firing counter order.
        
        Returns: con LF  = --:--
        """
        return self.query('CLC')
    
    def ReadQSCounterOrder(self):
        """Q-Switch counter order.
        
        Returns: con QS  = --:--
        """
        return self.query('CLQ')
    
    def ReadSimmerCounter(self):
        """Reading current simmer counter.
        
        Returns: cpt SIM = --:--
        """
        return self.query('LS')
    
    def ReadRepRateCounter(self):
        """Reading current rep. rate counter.
        
        Returns: cpt LF = --:--
        """
        return self.query('LC')
    
    def ReadSimmerCounter(self):
        """Reading current Q-Switch counter.
        
        Returns: cpt QS = --:--
        """
        return self.query('LQ')
    
    #################################################################
    ##########  Function time out (programming)            ##########
    #################################################################
    
    def SetTimeoutFn(self, config):
        """Sets Time out function.
        
        Valid range: 0 to 1 
        
        Returns: time out      1
        """
        return self.query('L'+str(config))
    
    def SetSimmerCounterOrder(self, config):
        """Sets simmer counter order.
        
        (Data is in minutes and seconds with maximum values 99 minutes
        and 59 seconds.)
        
        Returns: con SIM = 60:00
        """
        return self.query('CLS'+str(config))
    
    def SetFiringCounterOrder(self, config):
        """Sets firing counter order.
        
        (Data is in minutes and seconds with maximum values 99 minutes
        and 59 seconds.)
        
        Returns: con LF  = 01:00
        """
        return self.query('CLC'+str(config))
    
    def SetQSCounterOrder(self, config):
        """Sets Q-Switch counter order.
        
        (Data is in minutes and seconds with maximum values 99 minutes
        and 59 seconds.)
        
        Returns: con QS  = 01:00
        """
        return self.query('CLQ'+str(config))
