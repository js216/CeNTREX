import sys
sys.path.append('..')

from drivers import LakeShore218

with LakeShore218('COM3') as thermometer:
    print( thermometer.QueryIdentification() )
