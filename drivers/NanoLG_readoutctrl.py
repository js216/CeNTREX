import sys
sys.path.append('drivers/')
from NanoLG import NanoLG

class NanoLG_readoutctrl(NanoLG):
    def __init__(self, time_offset, com_port):
        super(NanoLG_readoutctrl, self).__init__(time_offset, 0)
