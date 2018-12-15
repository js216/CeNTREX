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
        try:
            return self.query('X')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadDateOfSoftwareReview(self):
        """Date of Software review (date/month/year).
        
        Returns: --/--/--       
        """
        try:
            return self.query('DAT')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
        
    def ReadCoolingGroupTempC(self):
        """Reads cooling group Temp ( C).
        
        Returns: temp. CG -- d  
        """
        try:
            return self.query('CG')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadCoolingGroupTempF(self):
        """Reads cooling group Temp ( F).
        
        Returns: temp. CG --- F 
        """
        try:
            return self.query('CGF')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadDispType(self):
        """Reads type of display ( C or  F).
        
        Returns: option TP  :  -
        """
        try:
            return self.query('NTP')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadCurrentConfig(self):
        """Read the current configuration.
        
        Returns: configuration -
        """
        try:
            return self.query('CFF')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadTimeCounter(self):
        """Time counter (When switch ON hhhh= number hours and mm=minutes).
        
        Returns: ct time hhhh:mm
        """
        try:
            return self.query('T')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadShutterState(self):
        """Reads shutter state.
        
        Returns: shutter closed 
                 shutter opened 
        """
        try:
            return self.query('R')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadShutterAtRun(self):
        """Reads open or close the shutter at run.
        
        Returns: shutt. at run -
        """
        try:
            return self.query('ROF')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadRackType(self):
        """The type of rack.
        
        Returns: option MPS :  -
        """
        try:
            return self.query('NPS')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadCapacitorType(self):
        """The type of capacitor.
        
        Returns: option CAP :  - 
        """
        try:
            return self.query('NCA')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadLaserType(self):
        """Read the type of laser (15 = version CFR).
        
        Returns: option B2K : 15
        """
        try:
            return self.query('NOP')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Configuration parameters (Programming)     ##########
    #################################################################
    
    def LoadNewConfig(self, config):
        """Loading a new configuration.
        
        Valid range: 1 -- 4
        
        Returns: configuration 1
        """
        try:
            return self.query('CFG'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SaveCurrentConfig(self, config):
        """Saving the current configuration.
        
        Valid range: 1 -- 4
        
        Returns: Save config.  2
        """
        try:
            return self.query('SAV'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetTempDispF(self, config):
        """Sets temperature display in  F.
        
        Valid range: 0 -- 1 (0 =  C, 1 =  F)
        
        Returns: option TP  :  1
        """
        try:
            return self.query('NTP'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetShutterOpen(self, config):
        """Sets opened or closed the shutter.
        
        Valid range: 0 -- 1
        
        Returns: shutter opened 
        """
        try:
            return self.query('R'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def OpenShutterAtRun(self, config):
        """Open or close the shutter at run.
        
        Valid range: 0 - 1 (1 = Open the shutter at run) 
        
        Returns: shutt. at run 1
        """
        try:
            return self.query('ROF'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
 
    def LaserStatus(self):
        """Status of laser.
        
        See manual (page 52) for interpretation of return value.

        Returns: I a F b S c Q d 
        """
        try:
            return self.query('WOR')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def LampQSStatus(self):
        """Reads the status of the lamp & QS operating mode.
        
        See manual for details (no idea which part of it!).
        """
        try:
            return self.query('')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Flashlamp parameters (Reading)             ##########
    #################################################################    
    
    def ReadFlashlampVoltage(self):
        """Flashlamp voltage (V).
        
        Returns: voltage  ---- V
        """
        try:
            return self.query('V')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadFlashlampTriggerMode(self):
        """Trigger Flashlamp mode.
        
        Returns: LP synch :  -  
        """
        try:
            return self.query('LPM')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadFlashlampRepRate(self):
        """Pre-set repetition rate (Hz).
        
        Returns: freq.  --.-- Hz
        """
        try:
            return self.query('F')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadFlashlampShotCounter(self):
        """Lamp shot counter (9 digits).
        
        Returns: ct LP ---------
        """
        try:
            return self.query('C')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadFlashlampUsersShotCounter(self):
        """Lamp User's shot counter (9 digits)
        
        Returns: cu LP ---------
        """
        try:
            return self.query('UC')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Flashlamp parameters (Programming)         ##########
    #################################################################
    
    def SetFlashlampTriggerMode(self, config):
        """Sets trigger Flashlamp mode.
        
        Valid range: 0 -- 1 (Internal trigger = 0 or External trigger = 1) 
        
        Returns: LP synch :  0  
        """
        try:
            return self.query('LPM'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan

    def SetFlashlampVoltage(self, config):
        """Flashlamp voltage (V).
        
        Valid range: 500 -- 1800 & Vmin < V < Vmax (factory set limits)
        
        Returns: voltage  0920 V
        """
        try:
            return self.query('V'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetFlashlampRepRate(self, config):
        """Sets repetition rate (Hz).
        
        Valid range: 1 -- 9999 
        
        Returns: freq.  12.25 Hz
        """
        try:
            return self.query('F'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ResetUsersLampShotCounter(self):
        """Reset Lamp User's shot counter.
        
        Valid range: 1 -- 9999 
        
        Returns: cu LP 000000000
        """
        try:
            return self.query('UC0')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Flashlamp activation/deactivation          ##########
    #################################################################
    
    def ActivateFlashlampAutoFire(self):
        """Activates automatic fire of lamp in the preselected
        operating mode.
        
        See manual (page 53) for details.
        """
        try:
            return self.query('A')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def StopFlashlampAutoFire(self):
        """Stops automatic internal or external lamp firing.
        
        See manual (page 53) for details.
        """
        try:
            return self.query('S')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetFlashlampSimmer(self):
        """Set the lamp on Simmer in the preselected operating mode.
        
        See manual (page 53) for details.
        """
        try:
            return self.query('S')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Q-switch parameters (Reading)              ##########
    #################################################################    
    
    def ReadQSMode(self):
        """Read Q-S mode.
        
        Returns: QS mode  :   -  
        """
        try:
            return self.query('QSM')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadQSAutoFn(self):
        """Read Q-S F/n in auto mode.
        
        Returns: cycle rate F/-- 
        """
        try:
            return self.query('QSF')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadQSNumPulsesBurstMode(self):
        """Read Q-S the number of pulses in burst mode.
        
        Returns: burst QS    ---
        """
        try:
            return self.query('QSP')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadTurnQSOnOff(self):
        """Turns Q-Switch ON or OFF.
        
        Returns: QS at run     -
        """
        try:
            return self.query('QOF')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadQSCount(self):
        """Q-Switch shot counter (9 digits).
        
        Returns: ct QS --------- 
        """
        try:
            return self.query('CQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadQSUsersCount(self):
        """Q-Switch User's shot counter (9 digits).
        
        Returns: cu QS --------- 
        """
        try:
            return self.query('UCQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadQSFlashlampDelay(self):
        """Delay between flashlamp & Q-S.
        
        Returns: delay    --- uS
        """
        try:
            return self.query('W')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadDelayQS1QS2(self):
        """Delay between Q-S1 & Q-S2. Only option double pulse.
        
        Returns: QS1-QS2  --- uS
        """
        try:
            return self.query('WD')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadVariableQSSynchroOut(self):
        """Variable QS synchro out (ns).
        
        Valid range: -500 to +500.
        
        Returns: var. QS +/- --- nS
        """
        try:
            return self.query('VQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Q-switch parameters (Reading)              ##########
    #################################################################  
    
    def SetQSBurstMode(self, config):
        """Sets Q-S mode burst. Auto = 0, Burst = 1 and Ext = 2.
        
        Returns: QS mode  :   1  
        """
        try:
            return self.query('QSM'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetQSF10(self, config):
        """Set Q-S F/10.
 
        Valid range: 1 to 99.
        
        Returns: cycle rate F/10
        """
        try:
            return self.query('QSF'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetQS50Bursts(self, config):
        """Sets Q-S 50 bursts.
        
        Valid range: 1 to 999
        
        Returns: burst QS    050
        """
        try:
            return self.query('QSP'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def TurnQSOn(self, config):
        """Turns Q-Switch ON.
        
        Valid range: 0 -- 1 (0=OFF, 1=ON)
        
        Returns: QS at run     1
        """
        try:
            return self.query('QOF'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ResetQSUserCounter(self):
        """Reset Q-Switch User's shot counter.

        Returns: cu QS 000000000
        """
        try:
            return self.query('UCQ0')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetQSFlashlampDelay(self, config):
        """Sets QS-Flash delay in us.
        
        Valid range: 80us to 999 us & Wmin < W< Wmax (factory set limits) 
        
        Returns: delay    225 uS
        """
        try:
            return self.query('W'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetQS1QS2Delay(self, config):
        """Sets delay between Q-S1 & Q-S2.
        
        Valid range : 30us to 250 us
        
        For one pulse sets value < 30.
        
        Returns: QS1-QS2  100 uS
        """
        try:
            return self.query('WD'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetVariableQSSynchroOut(self, config):
        """Sets Variable QS synchro out (ns).

        Valid range : -500ns to +500ns
        
        Returns: var. QS +250 nS
        """
        try:
            return self.query('VQ+'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadMinDelayQS(self):
        """Below limit delay QS.
        
        Returns: dly QS m --- uS 
        """
        try:
            return self.query('WMN')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadMaxDelayQS(self):
        """Above limit delay QS.
        
        Returns: dly QS M --- uS 
        """
        try:
            return self.query('WMX')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadNumPulsesWaitBeforeQS(self):
        """Number of pulses to wait after starting the lamp before
        enabling the q-switch.
        
        Returns: QS wait :  ---
        """
        try:
            return self.query('QSW')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadRamp(self):
        """Ramp in number of pulse Q-S.
        
        Valid range: 0 ^ 99 
        
        Returns: QS ramp :  ---
        """
        try:
            return self.query('QSR')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadRampStep(self):
        """Step of ramp Q-S in uS.

        Returns: tp QS min --d 
        """
        try:
            return self.query('TQN')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def MinTempQS(self):
        """Low limit temperature ( C) for QS.

        Returns: QS step : --uS 
        """
        try:
            return self.query('QSS')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Q-switch activation/deactivation           ##########
    #################################################################
    
    def StartQS(self):
        """Start Q-Switch laser emission in the preselected operating mode.
        
        See manual (page 54) for details.
        """
        try:
            return self.query('PQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def StopQS(self):
        """Stop Q-Switch laser emission.
        
        See manual (page 54) for details.
        """
        try:
            return self.query('SQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SinglePulseQS(self):
        """Single pulse Q-S laser emission in the preselected
        operating mode.
        
        See manual (page 55) for details.
        """
        try:
            return self.query('OQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Safety devices                             ##########
    #################################################################
    
    def TestFlashlampSafetyInterlock(self):
        """Test flashlamp safety interlock.
        
        See manual (page 55) for details.
        """
        try:
            return self.query('IF')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def TestQSSafetyInterlock(self):
        """Test Q-Switch safety devices.
        
        See manual (page 55) for details.
        """
        try:
            return self.query('IQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Function time out (reading)                ##########
    #################################################################
    
    def ReadTimeoutStatus(self):
        """Time out status.
        
        Returns: time out      -
        """
        try:
            return self.query('L')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadHarmonicGeneratorToTemp(self):
        """Harmonic Generator to temp.
        
        a=1 ready, a=1 not ready temp to low
        
        Returns: IHG           a
        """
        try:
            return self.query('IHG')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadSimmerCounterOrder(self):
        """Simmer counter order.
        
        Returns: con SIM = --:--
        """
        try:
            return self.query('CLS')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadFiringCounterOrder(self):
        """Firing counter order.
        
        Returns: con LF  = --:--
        """
        try:
            return self.query('CLC')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadQSCounterOrder(self):
        """Q-Switch counter order.
        
        Returns: con QS  = --:--
        """
        try:
            return self.query('CLQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadSimmerCounter(self):
        """Reading current simmer counter.
        
        Returns: cpt SIM = --:--
        """
        try:
            return self.query('LS')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadRepRateCounter(self):
        """Reading current rep. rate counter.
        
        Returns: cpt LF = --:--
        """
        try:
            return self.query('LC')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def ReadSimmerCounter(self):
        """Reading current Q-Switch counter.
        
        Returns: cpt QS = --:--
        """
        try:
            return self.query('LQ')
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    #################################################################
    ##########  Function time out (programming)            ##########
    #################################################################
    
    def SetTimeoutFn(self, config):
        """Sets Time out function.
        
        Valid range: 0 to 1 
        
        Returns: time out      1
        """
        try:
            return self.query('L'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetSimmerCounterOrder(self, config):
        """Sets simmer counter order.
        
        (Data is in minutes and seconds with maximum values 99 minutes
        and 59 seconds.)
        
        Returns: con SIM = 60:00
        """
        try:
            return self.query('CLS'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetFiringCounterOrder(self, config):
        """Sets firing counter order.
        
        (Data is in minutes and seconds with maximum values 99 minutes
        and 59 seconds.)
        
        Returns: con LF  = 01:00
        """
        try:
            return self.query('CLC'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
    
    def SetQSCounterOrder(self, config):
        """Sets Q-Switch counter order.
        
        (Data is in minutes and seconds with maximum values 99 minutes
        and 59 seconds.)
        
        Returns: con QS  = 01:00
        """
        try:
            return self.query('CLQ'+str(config))
        except pyvisa.errors.VisaIOError:
            logging.warning(str(time.time())+": pyvisa.errors.VisaIOError")
            return np.nan
