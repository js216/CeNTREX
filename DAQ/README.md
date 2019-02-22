# CeNTREX data acquisition software

   > "Still, I was accumulating experience and information, and I never threw
   > anything away. I kept files on everything. [...] I had a strict rule, which
   > I think secret services follow, too: No piece of information is superior to
   > any other. Power lies in having them all on file and then finding the
   > connections.  There are always connections; you have only to want to find
   > them.  [Umberto Ecco: Foucault's Pendulum] 

This is the software to control and record the parameters of the Centrex experiment.

## Program organization

The program's code is divided between classes that make up the graphical user
interface, and control classes which make use of driver classes (contained in
the `drivers` directory) to communicate with physical instruments. In addition,
all program configuration is contained in `.ini` files in subdirectories of the
`config` directory, allowing for simple modification and extension of the DAQ
system without changing the main program code.

There are three control classes:

- `Device` objects run each with its own thread, instantiate device drivers, and
  poll devices at regular intervals for data as well as check for normal
  operation insofar as supported by the driver, pushing this information into
  data and events queues specific to each device. In addition, these objects
  serve as an unified abstract interface to all the drivers and related
  information, especially through the `config` dictionary.

- `Monitoring`: While the `Device` objects collect information from the physical
  devices, they neither record it nor notify the user if any abnormal condition
  obtains. Thus the main program instantiates one `Monitoring` object to read
  some of the data, display it in the main interface, and send it to an external
  central database.

- `HDF_writer` writes all the data collected by `Device` objects to an HDF file
  for future reference and analysis.

The graphical user interface likewise consists of three parts. The user controls
the devices through the `ControlGUI`, which is a canvas for control of recording
and external devices such as temperature controllers and pulse tube compressors.
As detailed in the next section, the information in device config files is
automatically read and translated into usable controls that appear in the GUI.
`PlotsGUI` and `MonitoringGUI` are used, respectively, to make plots about the
data currently being collected, and to display the latest values measured. The
three parts of the GUI are held together by the `CentrexGUI` class which
instantiates them when the program is started.

The program is thus generic enough to make it easy to add capabilities to
control any number of new devices by simply (1) writing a device driver, and (2)
a device config file. The easiest way to do both of these things is to copy a
pre-existing driver and config file, and adapting to fit the new device.

## Configuration files

Upon starting, the program reads the main configuration file
`config/settings.ini` that defines general program settings; the values are read
into the `config` dictionary of the `CentrexGUI` class. In particular, the main
config file has to contain the following sections and fields:

      [general]
      run_name = 
      hdf_loop_delay = 

      [files]
      config_dir = 
      hdf_fname = 
      plotting_hdf_fname = 
      plotting_config_fname = 

      [influxdb]
      enabled = 
      host = 
      port = 
      username = 
      password = 
      database = 

The `config` dictionary will contain this and other information. In particular,
it also keeps track of the `time_offset` (see section on Data structure), as
well as whether control is currently running. Other GUI classes may also have a
`config` dictionary to contain metadata specific to them.  

Device configurations are read from `.ini` files in the chosen directory. (Thus
choosing a different directory allows for a different set of devices or device
configurations to be loaded.) These files have the structure:

    [device]
    ...
    
    [attributes]
    column_names = time, IG pressure
    units = s, torr
    ...

    [...]

The `[device]` section has to contain the parameters specified in the
`ControlGUI.read_device_config_options()` function. The `[attributes]` are
copied verbatim into the HDF file, and displayed in the `MonitoringGUI`. Any
following config file sections specify the controls to be displayed in
`ControlGUI`.

Four types of controls are supported: `Checkbutton`, `Entry`, `OptionMenu`, and
`Button`. All controls require a label (for `Button`s, it gets placed on the
button, for other controls, the label will appear to the left of the control),
the control type, and the `row`/`col` where they are to appear in the list of
controls for a given device. Some controls require other options (e.g.,
`Button`s need the device driver function that is called when the button is
pressed); see configuration files in `config/devices` for examples.

The information in these files is passed as a dictionary (named `config`) to the
constructor of `Device` objects. The dictionary itself is created when the
program initially reads the device configuration; see the function
`ControlGUI.read_device_config()` for details.

## Program operation

When the program is started, `ControlGUI` calls the `read_device_config()`
member function to attempt to read the configuration files in order to build the
graphical user interface consisting of controls for individual devices. The
program does not check the config files for syntax and its behaviour under
improperly formatted config files is undefined.

When the user starts control, the program attempts to talk to each of the
enabled devices to see if the expected response is received. Following that, it
starts the `HDF_writer` thread, which is thereby made ready to accept the data
that flows to it through the corresponding queues, and write it to the selected
HDF file. Then, each of the `Device` threads is started, cycling through a loop
of checking the device for abnormal conditions, recording numerical values, and
sending control commands to the device (and reading the values these commands
return). Finally, the `Monitoring` thread starts.

## Error handling

If a function has to stop due to an error condition, it should report the error
using the `logging.error()` function giving a descriptive message of what went
wrong, and return nothing:

    def myfunc():
       if error:
          logging.error("ERROR: an error has occurred.")
          return

If there is an abnormal condition that does not require the program to
terminate, it should be reported via the `logging.warning()` function.

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

- `CPA1110`, the compressor for pulse tube refrigerators
- `CTC100`, the thermal controller from Stanford instruments
- `HiPace700`, or any Pfeiffer pump using the TC 400 controller
- `Hornet`, the Instrutech pressure gauge
- `HP6645A`, the GPIB-enabled power supply used for some constant heaters within
  the beam source
- `labjackT7`, the DAQ device used for controlling the high-voltage
  electrostatic lens electronics
- `LakeShore218`, thermometer controller
- `nXDS` for Edwards scroll pumps
- `PCIe5171` for the NI scope for the fast data acquisition
- `SynthHDPro`, used for generating microwaves for rotational cooling etc.
- `USB6008`, the NI DAQ device used for controlling the MKS 1179C mass flow
  controller, as well as a flood detector for the water-cooled PT compressors
- `WA1500`, the Burleigh wavemeter

Each driver, in addition to implementing all or some of the features of the
remote interface of the instrument, also defines the following functions:

- `__init__()`: the constructor for the driver
- `__enter__()` and `__exit()__`: functions required to enable use of the Python
  `with` statement
- `ReadValue()`: defines the default measurement parameter (e.g., for the
  LakeShore monitors, `ReadValue()` returns all the measured temperatures)
