import numpy as np
from numpy import sqrt
from calculate_levels import *
from states_operators import *
from hamiltonian import *
from track_levels import *
#from TlF_database import *


# Units and constants

Jmax = 6      # max J value in Hamiltonian
I_Tl = 1/2    # I1 in Ramsey's notation
I_F = 1/2     # I2 in Ramsey's notation

# TlF constants. Data from D.A. Wilkening, N.F. Ramsey,
# and D.J. Larson, Phys Rev A 29, 425 (1984). Everything in Hz.

Brot = 6689920000
c1 = 126030.0
c2 = 17890.0
c3 = 700.0
c4 = -13300.0

D_TlF = 4.2282 * 0.393430307 *5.291772e-9/4.135667e-15 # [Hz/(V/cm)]

# Constants from Wilkening et al, in Hz/Gauss, for 205Tl

mu_J = 35;
mu_Tl = 1240.5;
mu_F = 2003.63;

def calculate_levels(Ex, Ey, Ez, Bx, By, Bz):
    # db = LevelsDB('TlF.db')
    # db.create()

    H = np.load('hamiltonian_terms.npy')
    Hff_m, HSx_m, HSy_m, HSz_m, HZx_m, HZy_m, HZz_m = H

    energies, eigvecs = spectrum_sort(Ex, Ey, Ez, Bx, By, Bz, H)
    energies, eigvecs = sort_der2nd(energies, eigvecs)
    # db.insert_arrays(Ex, Ey, Ez, Bx, By, Bz, energies, eigvecs)
    # db.close()
    return energies, eigvecs
