# CeNTREX slow DAQ software

This repository has a very simple structure: `drivers` contains raw `.py` files
which define the classes that access devices through NI-VISA; `examples`
contains examples; `testing` has random stuff I'm working on.

## Recording

   > "Still, I was accumulating experience and information,
   > and I never threw anything away. I kept files on
   > everything. [...] I had a strict rule, which I think
   > secret services follow, too: No piece of information is
   > superior to any other. Power lies in having them all on
   > file and then finding the connections.  There are always
   > connections; you have only to want to find them.
   > [Umberto Ecco: Foucault's Pendulum] 

Let's store data in HDF5 files.

- Event Log
- Parameter Log
- Error handling
- Time synchronization

## Drivers

The drivers are Python modules stored in software/drivers.

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
- **Hornet IGM402:** Python wrapper for all the RS485 serial commands (using the ASCII protocol) supported by the Hot Cathode Ionization Vacuum Gauge With Dual Convection IGM402 Module, The Hornet.

#### Todo

- Vacuum pumps
- Pressure gauges

## User Interface

### Overview

- Status of recording controls.
- Graphical presentation of temperatures.
- Status of lasers.
- Vacuum chamber pressure.

### Recording

- Whether to record data, and what to record.
- Where to store data (filename or filename pattern).
- How to break long datasets amongst multiple files.
- Default sampling and display refresh rates.
- Synchronisation of date & time. Check with some online time source, and the Rb
  clock and GPS.
- Available disk space; current size of dataset.

### Thermal

- Full control of Lakeshore 218 and 330.
- Plots of all temperatures vs time (easy to change axes to look up past data).
- Heater selection module.

### Control of pulse tubes

A schematic like the one on the compressor package,

### Pressure

- Full control of pumps and pressure gauges.

### Lasers

- Ablation laser parameters.
- Maximize laser power with respect to flashlamp-QS delay.

### Environment

- Room temperature & humidity for main lab and compressor cabinet.

### Remote access

- Access from smartphones (Android) and everywhere around the world would be
  nice.
