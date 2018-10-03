import sys
sys.path.append('..')
import pyvisa

from drivers import LakeShore218
from drivers import LakeShore330

rm = pyvisa.ResourceManager()

with LakeShore218(rm, 'COM6') as thermometer:
    print( thermometer.QueryIdentification() )
    with LakeShore330(rm, 'GPIB0::16') as thermometer2:
        print( thermometer2.QueryIdentification() )
