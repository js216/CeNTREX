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

## Program organization

The main program is an object of the `CentrexGUI` class. It reads the
configuration files when it starts (through the `read_config()` function), then
instantiates the classes that draw the graphical user interface. Note that the
program does not write to the configuration files.

So far, the only implemented GUI class is `ControlGUI`, which is a canvas for
control of recording and external devices such as temperature controllers and
pulse tube compressors. As detailed in the next section, the information in
device config files is automatically read and translated into usable controls
that appear in the GUI.

However, the controls in `ControlGUI` do not access the drivers, let alone the
devices, directly. Instead, `ControlGUI` instantiates `Device` objects that in
communicate with the drivers to record parameters and pass commands to the
external devices. This enables thread-based parallelism; each `Device` instance
runs in a separate thread for quasi-synchronous control of devices.

## Configuration files

Upon starting, the program reads the general configuration file
`config/settings.ini` that defines general program settings; the values are read
into the `config` dictionary.

Device configurations are read from `.ini` files in the `config/devices`
directory. These files have the structure:

    [device]
    name = Hornet               # name of device as used internally by the program
    label = Hornet              # name of the device as displayed by the program
    path = beam_source/pressure # where to store the numerical CSV/HDF data
    driver = Hornet             # name of the driver class
    constr_params = COM_port    # parameters to be passed to the driver constructor
    correct_response = True     # for connection testing
    row = 0                     # row in the main program to place the controls in
    column = 0                  # column for the same
    
    [attributes]                # attributes to be stored with the HDF dataset
    column_names = time, IG pressure
    units = s, torr
    ...

    [...]                      # any number of further controls for the device

Four types of controls are supported: `Checkbutton`, `Entry`, `OptionMenu`, and
`Button`. All controls require a label (for `Button`s, it gets placed on the
button, for other controls, the label will appear to the left of the control),
the control type, and the `row`/`col` where they are to appear in the list of
controls for a given device. Some controls require other options (e.g.,
`Button`s need the device driver function that is called when the button is
pressed); see configuration files in `config/devices` for examples.

The information in these files is passed as a dictionary (named `config`) to the
constructor of `Device` objects:

    config = {
       "name"              : ...,
       "label"             : ...,
       "config_fname"      : ....,  # name of the device config file
       "current_run_dir"   : ...,   # where the CSV files are to be stored
       "path"              : ...,
       "correct_response"  : ...,
       "row"               : ...,
       "column"            : ...,
       "driver"            : ...,
       "attributes"        : ...,   # dictionary of above-listed attributes
       "controls"          : ...,
    }

Most elements here are already explained above. The `controls` dictionary is to
contain everything related to the control of the device: the GUI elements, the
related variables, etc.

## Data structure

The data from each run is initially stored in a series of CSV files for
robustness and ease of monitoring. When the trial is completed, the user is
encouraged to push the data to a HDF5 file by pressing the "Write to HDF"
button, or invoking the `write_to_HDF()` function.

In the HDF file, each experimental run (e.g. initial pumpdown, testing the pulse
tube cooling / heaters, etc.) is its own group. Each of these groups in turn
contains subgroups:

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

- more drivers
   - flood control and MKS control
   - Vacuum pumps
   - Room temperature & humidity for main lab and compressor cabinet.
- status tab
   - current values of all parameters
   - adjustable plots of an arbitrary number of parameters
