#######################
### IMPORT PACKAGES ###
#######################

# import normal Python packages
import pyvisa
import time

# suppress weird h5py warnings
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import h5py
warnings.resetwarnings()

# import my device drivers
import sys
sys.path.append('..')
from drivers import Hornet 
from drivers import LakeShore218
from drivers import LakeShore330

########################
### DEFINE FUNCTIONS ###
########################

def create_database(fname):
    f = h5py.File(fname, 'w-')
    # groups
    root     = f.create_group("beam_source")
    pressure = root.create_group("pressure")
    thermal  = root.create_group("thermal")
    gas      = root.create_group("gas")
    lasers   = root.create_group("lasers")
    events   = root.create_group("events")
    # datasets
    length = 24*3600
    pressure.create_dataset("IG", (length,2), dtype='f', maxshape=(None,2))
    thermal.create_dataset("cryo", (length,13), dtype='f', maxshape=(None,13))

######################
### SET PARAMETERS ###
######################

fname = "C:/Users/CENTREX/Documents/data/pumpdown.h5"
create_database(fname)

###############################
### THE MAIN RECORDING LOOP ###
###############################

rm = pyvisa.ResourceManager()

with h5py.File(fname, 'r+') as f,\
 Hornet(rm, 'COM4') as ig,\
 LakeShore218(rm, 'COM1') as therm1,\
 LakeShore330(rm, 'GPIB0::16') as therm2:

     # open datasets
     ig_dset = f['beam_source/pressure/IG']
     therm_dset = f['beam_source/thermal/cryo']

     for i in range(12*3600):
         timestamp = time.time() - 1540324934
         ig_dset[i,0] = timestamp
         ig_dset[i,1] = ig.ReadSystemPressure()
         therm_dset[i,0] = timestamp
         therm_dset[i,1:9] = therm1.QueryKelvinReading()
         therm_dset[i,9] = therm2.ControlSensorDataQuery()
         therm_dset[i,10] = therm2.SampleSensorDataQuery()

         time.sleep(1)
