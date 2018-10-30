import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as md
import datetime as dt
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import h5py
warnings.resetwarnings()

# open file and read datasets
HDF_fname = "C:/Users/CENTREX/Documents/data/slow_data.h5"
f = h5py.File(HDF_fname, 'a')
root = f["cooldown and warming/beam_source"]
ig_dset = root["pressure/IG"]
cryo_dset = root["thermal/cryo"]

# format data
x = cryo_dset[:,0] + 1540324934 - 5*3600
dates=[dt.datetime.fromtimestamp(ts) for ts in x]
datenums=md.date2num(dates)
y1 = cryo_dset[:,1]
y2 = cryo_dset[:,2]
y3 = cryo_dset[:,3]
y4 = cryo_dset[:,4]
y5 = cryo_dset[:,5]
y6 = cryo_dset[:,6]
y7 = cryo_dset[:,7]
y8 = cryo_dset[:,8]
y9 = cryo_dset[:,9]
y11 = cryo_dset[:,10]

# plot data
plt.subplots_adjust(bottom=0.2)
plt.xticks( rotation=25 )
ax=plt.gca()
xfmt = md.DateFormatter('%Y-%m-%d %H:%M:%S')
ax.xaxis.set_major_formatter(xfmt)
plt.ylabel('temperature [K]')
plt.plot(datenums,y4,label="4K PT")
plt.plot(datenums,y2,label="4K shield top")
plt.plot(datenums,y6,label="4K shield bottom")
plt.plot(datenums,y8,label="16K PT")
plt.plot(datenums,y1,label="cell back snorkel")
plt.plot(datenums,y5,label="cell top plate")
plt.plot(datenums,y9,label="cell input nozzle")
plt.plot(datenums,y3,label="40K shield top")
plt.plot(datenums,y7,label="40K shield bottom")
plt.plot(datenums,y11,label="4K PT warm stage")
plt.legend()
plt.show()
