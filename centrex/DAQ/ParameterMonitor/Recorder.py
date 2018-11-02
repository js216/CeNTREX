#######################
### IMPORT PACKAGES ###
#######################

# import normal Python packages
import pyvisa
import time
import numpy as np
import csv
import logging
import os

# import my device drivers
import sys
sys.path.append('..')
from drivers import Hornet 
from drivers import LakeShore218
from drivers import LakeShore330
from drivers import CPA1110

########################
### DEFINE FUNCTIONS ###
########################

def clear_temp_dir(temp_dir):
    os.remove(temp_dir+'/ParameterMonitor.log')
    os.remove(temp_dir+"/time_offset")
    os.remove(temp_dir+"/beam_source/pressure/IG.csv")
    os.remove(temp_dir+"/beam_source/pressure/IG_params.csv")
    os.remove(temp_dir+"/beam_source/thermal/cryo_params.csv")
    os.remove(temp_dir+"/beam_source/thermal/cryo.csv")
    os.remove(temp_dir+"/beam_source/thermal/top_compressor.csv")
    os.remove(temp_dir+"/beam_source/thermal/top_compressor_params.csv")
    os.remove(temp_dir+"/beam_source/thermal/bottom_compressor.csv")
    os.remove(temp_dir+"/beam_source/thermal/bottom_compressor_params.csv")

def run_recording(temp_dir, N, dt):
    """Record N datapoints every dt seconds to CSV files in temp_dir."""

    # select and record the time offset
    time_offset = time.time()
    with open(temp_dir+"/time_offset",'w') as to_f:
        to_f.write(str(time_offset))
    def timestamp():
        return time.time() - time_offset

    # open files and devices
    rm = pyvisa.ResourceManager()
    with open(temp_dir+"/beam_source/pressure/IG.csv",'a',1) as ig_f,\
         open(temp_dir+"/beam_source/pressure/IG_params.csv",'a',1) as ig_params_f,\
         open(temp_dir+"/beam_source/thermal/cryo_params.csv",'a',1) as cryo_params_f,\
         open(temp_dir+"/beam_source/thermal/cryo.csv",'a',1) as cryo_f,\
         open(temp_dir+"/beam_source/thermal/top_compressor.csv",'a',1) as tc_f,\
         open(temp_dir+"/beam_source/thermal/top_compressor_params.csv",'a',1) as tc_params_f,\
         open(temp_dir+"/beam_source/thermal/bottom_compressor.csv",'a',1) as bc_f,\
         open(temp_dir+"/beam_source/thermal/bottom_compressor_params.csv",'a',1) as bc_params_f,\
         CPA1110('COM10')               as top_compressor,\
         CPA1110('COM11')               as bottom_compressor,\
         Hornet(rm, 'COM4')            as ig,\
         LakeShore218(rm, 'COM1')      as therm1,\
         LakeShore330(rm, 'GPIB0::16') as therm2:

        # create csv writers
        ig_dset = csv.writer(ig_f)
        ig_params = csv.writer(ig_params_f)
        cryo_dset = csv.writer(cryo_f)
        cryo_params = csv.writer(cryo_params_f)
        tc_dset = csv.writer(tc_f)
        tc_params= csv.writer(tc_params_f)
        bc_dset = csv.writer(bc_f)
        bc_params= csv.writer(bc_params_f)

        # record operating parameters
        ig_params.writerow( ["IG filament current", "100", "microamps"] )
        ig_params.writerow( ["units", "s", "torr"] )
        ig_params.writerow( ["column_names", "time", "IG pressure"] )
        cryo_params.writerow( ["units", "s", "K", "K", "K", "K", "K", "K", "K", "K", "K", "K"] )
        cryo_params.writerow( ["column_names", "time", "cell back snorkel", "4K shield top",
                "40K shield top", "40K PT cold head", "cell top plate", "4K shield bottom",
                "40K shield bottom", "16K PT cold head", "cell input nozzle", "4K PT warm stage"] )
        tc_params.writerow( ["column_names", "time", "CoolantInTemp",
            "CoolantOutTemp", "OilTemp", "HeliumTemp", "LowPressure",
            "LowPressureAverage", "HighPressure", "HighPressureAverage",
            "DeltaPressureAverage", "MotorCurrent"] )
        tc_params.writerow( ["units", "s", "F", "F", "F", "F", "psi", "psi",
            "psi", "psi", "psi", "amps"] )
        bc_params.writerow( ["column_names", "time", "CoolantInTemp",
            "CoolantOutTemp", "OilTemp", "HeliumTemp", "LowPressure",
            "LowPressureAverage", "HighPressure", "HighPressureAverage",
            "DeltaPressureAverage", "MotorCurrent"] )
        bc_params.writerow( ["units", "s", "F", "F", "F", "F", "psi", "psi",
            "psi", "psi", "psi", "amps"] )

        # main recording loop
        for i in range(N):
            ig_dset.writerow( [timestamp(), ig.ReadSystemPressure()] )
            cryo_dset.writerow( [timestamp()] + therm1.QueryKelvinReading() +
                [therm2.ControlSensorDataQuery(), therm2.SampleSensorDataQuery()] )
            top_compressor.ReadRegisters()
            tc_dset.writerow( [timestamp(), top_compressor.CoolantInTemp(),
                top_compressor.CoolantOutTemp(), top_compressor.OilTemp(),
                top_compressor.HeliumTemp(), top_compressor.LowPressure(),
                top_compressor.LowPressureAverage(),
                top_compressor.HighPressure(),
                top_compressor.HighPressureAverage(),
                top_compressor.DeltaPressureAverage(),
                top_compressor.MotorCurrent()] )
            bottom_compressor.ReadRegisters()
            bc_dset.writerow( [timestamp(), bottom_compressor.CoolantInTemp(),
                bottom_compressor.CoolantOutTemp(), bottom_compressor.OilTemp(),
                bottom_compressor.HeliumTemp(), bottom_compressor.LowPressure(),
                bottom_compressor.LowPressureAverage(),
                bottom_compressor.HighPressure(),
                bottom_compressor.HighPressureAverage(),
                bottom_compressor.DeltaPressureAverage(),
                bottom_compressor.MotorCurrent()] )
            time.sleep(dt)

#######################
### RUN THE PROGRAM ###
#######################

temp_dir = "C:/Users/CENTREX/Documents/data/current_run_dir"
logging.basicConfig(filename=temp_dir+'/ParameterMonitor.log')
#clear_temp_dir(temp_dir)
run_recording(temp_dir, 5*24*3600*5, 0.2)
