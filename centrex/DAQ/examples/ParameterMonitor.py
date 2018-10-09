import sys
import pyvisa

sys.path.append('..')
from drivers import LakeShore218

rm = pyvisa.ResourceManager()

with LakeShore218(rm, 'COM6') as th:
    print( th.QueryKelvinReading(1) )
