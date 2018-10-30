#######################
### IMPORT PACKAGES ###
#######################

# import normal Python packages
import numpy as np
import time

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
    ig_params_CSV = np.loadtxt(CSV_dir+"/beam_source/pressure/IG_params.csv", delimiter=',')
    cryo_CSV = np.loadtxt(CSV_dir+"/beam_source/thermal/cryo.csv", delimiter=',')
    cryo_params_CSV = np.loadtxt(CSV_dir+"/beam_source/thermal/cryo_params.csv", delimiter=',')

    # write HDF datasets
    ig_dset = pressure.create_dataset("IG", data=ig_CSV, dtype='f')
    cryo_dset = thermal.create_dataset("cryo", data=cryo_CSV, dtype='f')

    # write attributes to HDF
    for col in cryo_params_CSV:
        if len(col) == 2:
            cryo_dset.attrs[col[0]] = col[1]
        else:
            cryo_dset.attrs[col[0]] = col[1:]
    for col in ig_params_CSV:
        if len(col) == 2:
            ig_dset.attrs[col[0]] = col[1]
        else:
            ig_dset.attrs[col[0]] = col[1:]

    # record the arbitrary time offset
    with open(CSV_dir+"/time_offset",'r') as to_f:
        ig_dset.attrs['time_offset']   = to_f.read()
        cryo_dset.attrs['time_offset'] = to_f.read()

###################################
### USE FUNCTIONS (for testing) ###
###################################

temp_dir = "C:/Users/CENTREX/Documents/data/current_run_dir"
HDF_fname = "C:/Users/CENTREX/Documents/data/slow_data_test.h5"
run_name = str(int(time.time())) + " cooldown and warming"
CSV_into_HDF5(temp_dir, HDF_fname, run_name)
