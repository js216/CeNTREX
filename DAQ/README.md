# CeNTREX slow DAQ software

   > "Still, I was accumulating experience and information,
   > and I never threw anything away. I kept files on
   > everything. [...] I had a strict rule, which I think
   > secret services follow, too: No piece of information is
   > superior to any other. Power lies in having them all on
   > file and then finding the connections.  There are always
   > connections; you have only to want to find them.
   > [Umberto Ecco: Foucault's Pendulum] 

This is the software to control and record parameters of the Centrex experiment.

## Data structure

Let's store data in an HDF5 file. Each experimental run (e.g. initial pumpdown,
testing the pulse tube cooling / heaters, etc.) is its own group. Each of these
groups in turn contains subgroups:

     /beam_source/pressure
                  thermal
                  ...

The datasets in these groups are rows of single-precision (i.e. 4-byte)
floating-point datapoints, where the first column is always the UNIX time of
when the data was taken, offset by the time the run was begun.

Ofsetting the time allows us to store the data as single-precision floats. These
have ~7.2 decimal digits of precision; if we want timestamps to be specified
down to 1 second of precision, a single run can be recorded for up to ~115 days.
(Using double-precision floats would eliminate the need for the time offset, but
would require twice as much storage space.) The time offset is recorded as the
`time_offset` attribute of each dataset; other attributes provide column names,
units, and other additional information (e.g., ion gauge emission current
setting).

## Drivers

The drivers are Python modules stored in `drivers`.

- **Lakeshore 330 temperature controller:** Python wrapper for all the
  IEEE-488/serial commands supported by the Lake Shore Model 330 Autotuning
  Temperature Controller.
- **Lakeshore 218 temperature monitor:** Python wrapper for all the serial
  commands supported by the Lake Shore Model 330 eight input temperature
  monitor.
- **Big Sky Laser CFR 200 (ablation laser):** Python wrapper for all the serial
  commands supported by the Big Sky Laser CFR 200 Nd:YAG Laser System.
- **Tektronix 2014B scope:** a subset of the interface described in the
  Programmer Manual.
- **Cryomech CPA1110:** the entire interface from the manual.
- **MKS 1179C:** Python interface for all the control lines of the MKS 1179C
  General Purpose Mass-Flo® Controller, as controlled by a NI USB-6008
  Multifunction I/O Device.
- **Hornet IGM402:** Python wrapper for all the RS485 serial commands (using the
  ASCII protocol) supported by the Hot Cathode Ionization Vacuum Gauge With Dual
  Convection IGM402 Module, The Hornet.

## Todo

- recording
   - Available disk space; current size of dataset.
   - deal with excessive number of np.nan returns
   - make the attributes dialog box
   - hoover tooltip for the dt Entry
   - make resizing work correctly
   - make tabs
- more drivers
   - Vacuum pumps
   - counter for the atomic clock
   - Room temperature & humidity for main lab and compressor cabinet.
- overview tab
   - Status of recording controls.
   - Graphical presentation of temperatures.
   - Status of lasers.
   - Vacuum chamber pressure.
- control tab
   - Full control of Lakeshore 218 and 330.
   - Plots of all temperatures vs time (easy to change axes to look up past data).
   - Heater selection module.
   - A schematic like the one on the PT compressor package
   - Full control of pumps and pressure gauges.
   - Ablation laser parameters.
