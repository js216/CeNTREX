#######################
### IMPORT PACKAGES ###
#######################

# import normal Python packages
import numpy as np

# suppress weird h5py warnings
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import h5py
warnings.resetwarnings()

########################
### DEFINE FUNCTIONS ###
########################

def create_database(fname, length):
    """Create a new HDF5 file, defining the data structure."""

    f = h5py.File(fname, 'w-')

    # groups
    root     = f.create_group("beam_source")
    pressure = root.create_group("pressure")
    thermal  = root.create_group("thermal")
    gas      = root.create_group("gas")
    lasers   = root.create_group("lasers")
    events   = root.create_group("events")

    # datasets
    length = length
    ig_dset = pressure.create_dataset("IG", (length,2), dtype='f', maxshape=(None,2))
    ig_dset.set_fill_value = np.nan
    t_dset = thermal.create_dataset("cryo", (length,13), dtype='f', maxshape=(None,13))
    t_dset.set_fill_value = np.nan
