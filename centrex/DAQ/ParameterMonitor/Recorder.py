#######################
### IMPORT PACKAGES ###
#######################

# import normal Python packages
import pyvisa
import time
import numpy as np
import csv
import logging

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

def timestamp():
    return time.time() - 1540324934

def run_recording(temp_dir, N, dt):
    """Record N datapoints every dt seconds to CSV files in temp_dir."""

    # open files and devices
    rm = pyvisa.ResourceManager()
    with open(temp_dir+"/beam_source/pressure/IG.csv",'a',1) as ig_f,\
         open(temp_dir+"/beam_source/thermal/cryo.csv",'a',1) as cryo_f,\
         Hornet(rm, 'COM4')            as ig,\
         LakeShore218(rm, 'COM1')      as therm1,\
         LakeShore330(rm, 'GPIB0::16') as therm2:

        # create csv writers
        ig_dset = csv.writer(ig_f)
        cryo_dset = csv.writer(cryo_f)

        # main recording loop
        for i in range(N):
            ig_dset.writerow( [timestamp(), ig.ReadSystemPressure()] )
            cryo_dset.writerow( [timestamp()] + therm1.QueryKelvinReading() +
                [therm2.ControlSensorDataQuery(), therm2.SampleSensorDataQuery()] )
            time.sleep(dt)

#######################
### RUN THE PROGRAM ###
#######################

temp_dir = "C:/Users/CENTREX/Documents/data/temp_run_dir"
logging.basicConfig(filename=temp_dir+'ParameterMonitor.log')
run_recording(temp_dir, 5*24*3600, 1)
