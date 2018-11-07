#######################
### IMPORT PACKAGES ###
#######################

# import normal Python packages
import numpy as np
import time
import csv

# suppress weird h5py warnings
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import h5py
warnings.resetwarnings()

########################
### DEFINE FUNCTIONS ###
########################

def asc(unicode_list):
    """Convert list of Unicode strings to a list of ASCII strings.

    HDF5 cannot take Unicode strings, while Python3 strings are Unicode by
    default.
    """
    return [s.encode('ascii') for s in unicode_list]

def CSV_into_HDF5(CSV_dir, HDF_fname, run_name):
    """Read a directory of CSV files into an HDF5 file."""

    # open file
    f = h5py.File(HDF_fname, 'a')
    root = f.create_group(run_name)

    # create groups
    bs       = root.create_group("beam_source")
    pressure = bs.create_group("pressure")
    thermal  = bs.create_group("thermal")
    gas      = bs.create_group("gas")
    lasers   = bs.create_group("lasers")
    events   = bs.create_group("events")

    # read CSV files
    ig_CSV = np.loadtxt(CSV_dir+"/beam_source/pressure/IG.csv", delimiter=',')
    cryo_CSV = np.loadtxt(CSV_dir+"/beam_source/thermal/cryo.csv", delimiter=',')
    tc_CSV = np.loadtxt(CSV_dir+"/beam_source/thermal/top_compressor.csv", delimiter=',')
    bc_CSV = np.loadtxt(CSV_dir+"/beam_source/thermal/bottom_compressor.csv", delimiter=',')

    # write HDF datasets
    ig_dset = pressure.create_dataset("IG", data=ig_CSV, dtype='f')
    cryo_dset = thermal.create_dataset("cryo", data=cryo_CSV, dtype='f')
    tc_dset = thermal.create_dataset("top_compressor", data=tc_CSV, dtype='f')
    bc_dset = thermal.create_dataset("bottom_compressor", data=bc_CSV, dtype='f')

    # write attributes to HDF
    with open(CSV_dir+"/beam_source/pressure/IG_params.csv", 'r', newline='\n') as ig_params_f:
        ig_params_CSV = csv.reader(ig_params_f, delimiter=',')
        for col in ig_params_CSV:
            if len(col) == 2:
                ig_dset.attrs[col[0]] = col[1]
            else:
                ig_dset.attrs[col[0]] = asc(col[1:])
    with open(CSV_dir+"/beam_source/thermal/cryo_params.csv", 'r', newline='\n') as cryo_params_f:
        cryo_params_CSV = csv.reader(cryo_params_f, delimiter=',')
        for col in cryo_params_CSV:
            if len(col) == 2:
                cryo_dset.attrs[col[0]] = col[1]
            else:
                cryo_dset.attrs[col[0]] = asc(col[1:])
    with open(CSV_dir+"/beam_source/thermal/top_compressor_params.csv", 'r', newline='\n') as tc_params_f:
        tc_params_CSV = csv.reader(tc_params_f, delimiter=',')
        for col in tc_params_CSV:
            if len(col) == 2:
                tc_dset.attrs[col[0]] = col[1]
            else:
                tc_dset.attrs[col[0]] = asc(col[1:])
    with open(CSV_dir+"/beam_source/thermal/bottom_compressor_params.csv", 'r', newline='\n') as bc_params_f:
        bc_params_CSV = csv.reader(bc_params_f, delimiter=',')
        for col in bc_params_CSV:
            if len(col) == 2:
                bc_dset.attrs[col[0]] = col[1]
            else:
                bc_dset.attrs[col[0]] = asc(col[1:])

    # record the arbitrary time offset
    with open(CSV_dir+"/time_offset",'r') as to_f:
        time_offset = to_f.read()
        ig_dset.attrs['time_offset']   = time_offset
        cryo_dset.attrs['time_offset'] = time_offset
        tc_dset.attrs['time_offset'] = time_offset
        bc_dset.attrs['time_offset'] = time_offset

###################################
### USE FUNCTIONS (for testing) ###
###################################

temp_dir = "C:/Users/CENTREX/Documents/data/current_run_dir"
#HDF_fname = "C:/Users/CENTREX/Documents/data/slow_data_test.h5"
HDF_fname = "C:/Users/CENTREX/Documents/data/slow_data.h5"
run_name = str(int(time.time())) + " " + "heater control 10K to 16K, and then 18K, test"
CSV_into_HDF5(temp_dir, HDF_fname, run_name)
