from drivers.Bristol671A import *
from drivers.SelfAlignFiberSwitch import *

class WavemeterFiberswitch:
    def __init__(self, time_offset, connection_wavemeter, COM_port_fiberswitch, ports):
        self.time_offset    = time_offset

        if COM_port_fiberswitch not in ['client', '']:
            self.wavemeter      = Bristol671A(time_offset, connection_wavemeter)
            self.switch         = SelfAlignFiberSwitch(time_offset, COM_port_fiberswitch)

            self.verification_string = self.wavemeter.verification_string + ', '
            self.verification_string += self.switch.verification_string
        else:
            self.verification_string = 'BRISTOL WAVELENGTH METER, 671A-VIS, 6894, 1.2.0, True'

        if not isinstance(ports, (tuple, list)):
            self.ports = [int(p) for p in ports.split(',')]
        else:
            self.ports = ports

        self.dtype = tuple(['f8'] * (len(self.ports)+1))
        self.shape = (1+len(self.ports),)

        self.new_attributes = []
        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.wavemeter.__exit__(exc)
        self.switch.__exit__(exc)

    def GetWarnings(self):
        warnings = self.warnings.copy()
        warnings.extend(self.wavemeter.GetWarnings())
        warnings.extend(self.switch.GetWarnings())
        self.warnings = []
        return warnings

    def ReadValue(self):
        port = self.switch.ReadValue()
        t, frequency = self.wavemeter.ReadValue()
        frequencies = [np.nan]*len(self.ports)

        if isinstance(port, (list, tuple)):
            port = port[1]
            frequencies[self.ports.index(port)] = frequency

        return [t]+frequencies

    def SetPort(self,port):
        try:
            port = int(port)
        except Exception as err:
            logging.warning("SelfAlignFiberSwitch warning in Setport : can't convert {0} to int".format(port))
            warning_dict = { "Setport; can't convert {0} to int".format(port)}
            self.warnings.append([time.time(), warning_dict])
        if port in self.ports:
            self.switch.SetPort(port)
        else:
            logging.warning("WavemeterFiberswitch warning in Setport : port {0} not connected".format(port))
            warning_dict = { "Setport; can't convert {0} to int".format(port)}
            self.warnings.append([time.time(), warning_dict])
