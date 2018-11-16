# CeNTREX slow DAQ software

   > "Still, I was accumulating experience and information,
   > and I never threw anything away. I kept files on
   > everything. [...] I had a strict rule, which I think
   > secret services follow, too: No piece of information is
   > superior to any other. Power lies in having them all on
   > file and then finding the connections.  There are always
   > connections; you have only to want to find them.
   > [Umberto Ecco: Foucault's Pendulum] 

This is the software to control and record the parameters of the Centrex experiment.

## Configuration files

Upon starting, the program reads the general configuration file
`config/settings.ini` that defines general program settings; the values are read
into the `config` dictionary.

Device configurations are read from `.ini` files in the `config/devices`
directory. These files have the structure:

    [device]
    name = bottom_compressor   # name of device as used internally by the program
    label = Bottom compressor  # name of the device as displayed by the program
    path = beam_source/thermal # where to store the numerical CSV/HDF data
    driver = CPA1110           # name of the driver class
    correct_response = 50306   # for connection testing

    [attributes]               # attributes to be stored with the HDF dataset
    units = s, F, F, F, F, psi, psi, psi, psi, psi, amps
    ...

    [enabled]
    type = Checkbutton
    value = 1

    [dt]                       # loop delay
    type = Entry
    value = 1.0

    [...]                      # any number of further controls for the device
    ...

The information in these files is passed as a dictionary to the constructor of
`Device` objects:

    dev_config = {
                "name"              : params["device"]["name"],
                "label"             : params["device"]["label"],
                "path"              : params["device"]["path"],
                "correct_response"  : params["device"]["correct_response"],
                "driver"            : eval(paramsdevice[]["driver"]),
                "attributes"        : params["attributes"],
                "controls"          : {},
            }

Most elements here are already explained above. The `controls` dictionary is to
contain everything related to the control of the device: the GUI elements, the
related variables, etc.

## Data structure

The data is to be stored in an HDF5 file. Each experimental run (e.g. initial
pumpdown, testing the pulse tube cooling / heaters, etc.) is its own group. Each
of these groups in turn contains subgroups:

     /beam_source/pressure
                  thermal
                  ...

The datasets in these groups are rows of single-precision (i.e. 4-byte)
floating-point datapoints, where the first column is always the UNIX time of
when the data was taken, offset by the time the run was begun.

Offsetting the time allows us to store the data as single-precision floats. These
have ~7.2 decimal digits of precision; if we want timestamps to be specified
down to 1 second of precision, a single run can be recorded for up to ~115 days.
(Using double-precision floats would eliminate the need for the time offset, but
would require twice as much storage space.) The time offset is recorded as the
`time_offset` attribute of each dataset; other attributes provide column names,
units, and other additional information as relevant (e.g., ion gauge emission
current setting).

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

Each driver, in addition to implementing all or some of the features of the
remote interface of the instrument, also defines the following functions:

- `__init__()`: the constructor for the driver
- `__enter__()` and `__exit()__`: functions required to enable use of the Python
  `with` statement
- `ReadValue()`: defines the default measurement parameter (e.g., for the
  LakeShore monitors, `ReadValue()` returns all the measured temperatures)
- `VerifyOperation()`: returns a string characteristic of the instrument, used
  to verify the instrument is connected correctly

## Todo

- general
   - make the "refresh COM port" button work
   - check that the files have been successfully deleted
   - make the loop delay changable while running
   - don't depend on dictionary to be ordered: have row/column for each control
   - Hornet IG control should be buttons
   - LakeShore330 setpoint control
   - describe Program Organization in the readme
   - commands and errors should be recorded in the event log
   - make tabs
- recording
   - Available disk space; current size of dataset.
   - refresh COM ports after starting the program, not before
   - deal with excessive number of np.nan returns
   - `write_to_HDF()` should only write the enabled devices
   - make the attributes dialog box
   - hoover tooltip for the dt Entry
   - make resizing work correctly
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
