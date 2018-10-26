import numpy as np
import matplotlib.pyplot as plt

temp_dir = "C:/Users/CENTREX/Documents/data/temp_run_dir"

with open(temp_dir+"/beam_source/pressure/IG.csv",'r+') as ig_f:
    ig_dset = np.loadtxt(ig_f)

plt.axis([0, 50, 0, 1])

for i in range(50):
    y = np.random.random()
    plt.scatter(i, y)
    plt.pause(0.1)

plt.show()
