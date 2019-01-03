import niscope
import numpy as np
from tqdm import tqdm
import h5py

def acquire_waveforms(fname, channel, nrSamples, samplingRate, bandwidth, iterations, compression = None):
    with niscope.Session("PXI1Slot2") as session:
        session.binary_sample_width = 16
        session.max_input_frequency = bandwidth
        session.channels[channel].configure_vertical(range=5.0, coupling=niscope.VerticalCoupling.AC)
        session.configure_horizontal_timing(min_sample_rate=int(samplingRate), min_num_pts=int(nrSamples), ref_position=50.0, num_records=1, enforce_realtime=True)

        waveform = np.ndarray(nrSamples, dtype = np.int16)
        for iteration in tqdm(range(iterations)):
            waveform = np.ndarray(nrSamples, dtype = np.int16)
            with session.initiate():
                info = session.channels[channel].fetch_into(waveform, num_records=1)[0]

            with h5py.File(fname+'.hdf5', 'a') as f:
                if '/waveforms' not in f:
                    grp = f.create_group('waveforms')
                else:
                    grp = f['waveforms']
                if compression == None:
                    dset = grp.create_dataset("record_{0}".format(iteration), (nrSamples, ), dtype = np.int16)
                else:
                    dset = grp.create_dataset("record_{0}".format(iteration), (nrSamples, ), dtype = np.int16, compression="gzip", compression_opts = compression)
                dset[:] = waveform
                dset.attrs['gain'] = info.gain
                dset.attrs['offset'] = info.offset
                dset.attrs['x_increment'] = info.x_increment
                dset.attrs['absolute_initial_x'] = info.absolute_initial_x
