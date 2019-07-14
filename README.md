# CeNTREX data acquisition software

   > "Still, I was accumulating experience and information, and I never threw
   > anything away. I kept files on everything. [...] I had a strict rule, which
   > I think secret services follow, too: No piece of information is superior to
   > any other. Power lies in having them all on file and then finding the
   > connections. There are always connections; you have only to want to find
   > them. [Umberto Ecco: Foucault's Pendulum] 

This is the software to control and record the parameters of the Centrex experiment.

## Program organization

The program's code is divided between classes that make up the graphical user
interface, and control classes which make use of driver classes (contained in
the `drivers` directory) to communicate with physical instruments. In addition,
all program configuration is contained in `.ini` files in subdirectories of the
`config` directory, allowing for simple modification and extension of the DAQ
system without changing the main program code. This configuration is loaded into
the relevant `Config` class (e.g. `DeviceConfig`).

The user controls the devices through the `ControlGUI`, which is a canvas for
control of recording and external devices such as temperature controllers and
pulse tube compressors.  As detailed in the next section, the information in
device config files is automatically read and translated into usable controls
that appear in the GUI.

Underneath the graphical interface, three control classes implement the
program's functionality:

- `Device` objects run each within its own thread, instantiate device drivers,
  and poll devices at regular intervals for data as well as check for normal
  operation insofar as supported by the driver, pushing this information into
  data and events queues specific to each device. In addition, these objects
  serve as an unified abstract interface to all the drivers and related
  information, especially through the `config` member (of type `DeviceConfig`).

- `Monitoring`: While the `Device` objects collect information from the physical
  devices, they neither record it nor notify the user if any abnormal condition
  obtains. Thus the main program instantiates one `Monitoring` object to read
  some of the data, display it in the main interface, and send it to an external
  central database.

- `HDF_writer` writes all the data collected by `Device` objects to an HDF file
  for future reference and analysis.

The program is thus generic enough to make it easy to add capabilities to
control any number of new devices by simply (1) writing a device driver, and (2)
a device config file. The easiest way to do both of these things is to copy a
pre-existing driver and config file, and adapting to fit the new device.
Examples can be found in the `drivers/` and `config/` directories.

## Program operation

The exact order of events after the user starts control is specified in the
`ControlGUI.start_control()` function. Briefly, the program does the following:

   - check the control is not running already
   - select the time offset (see below in the section on Data structure)
   - setup & check connections of all `double_connect` devices; instantiate new
     Devices (Python threads can only be started once, so this allows
     re-starting stopped control)
   - connect device controls with the new instances of Devices
   - start the thread that writes to HDF
   - start control for all devices
   - update and start the monitoring thread
   - update program status
   - make all plots display the current run and file

Thereafter, the heart of the operation is the main loop in the `Device` class's
`run()` function. In pseudo-code, what takes place is roughly to following:

- Instantiate the device driver
- While device is enabled:
   - Sleep for the appropriate loop delay
   - Check device for abnormal conditions by calling the driver's
     `GetWarnings()` function
   - Call the driver's `ReadValue()` function, and push the results in the
     `data_queue and `plots_queue`
   - Keep track of the number of (sequential and total) NaN returns, and issue a
     warning if there's been too many sequential NaN returns
   - Send control commands, if any, to the device, and push the returned values
     to the `events_queue`
   - Send monitoring commands, if any, to the device, and push the returned
     values to the `monitoring_events_queue`
- Report any exception that has occurred in the `run()` function

The loop delay approximately determines the rate of collecting data. Since
serial connection takes a random amount of time to return data, this approach
does not allow polling devices at exact intervals.

When the user stops control, the `ControlGUI.stop_control()` function is called,
going through the following sequence of events:

- Check the program is not stopped already
- Stop all plots
- Stop monitoring
- Stop the HDF writer
- For each Device thread:
   - Check device is active
   - Reset all indicators to the default value
   - Stop the device, waiting for it to finish
- Update the program status label

## Data flow

The following paragraphs describe how data flow works in general. The details
are likely to change as the program evolves, and code should be consulted.

The `Device` instances push data read from the driver to a `deque` called
`data_queue`. They also push a copy of the same data to the `plots_queue`, which
allows us to plot data from memory instead of having to open the HDF file each
time a plot needs to be updated. The events associated with user or
`Monitoring` commands are pushed to the appropriate events queues.

The HDF writer reads from the `data_queue` as well as the `events_queue`.
`Monitoring` monitors the length of the `data_queue`, but reads from the
`plots_queue`, and also empties the `data_queue` and the `events_queue` if the
HDF writer is disabled. In that case, if it cannot get events from the HDF file,
it also obtains the data from `events_queue` before emptying it.

The `Config` classes serve to make access to program/device/plot configuration
systematic. Thus, instead of having classes pass ad hoc pieces of information
between each other, they should set an appropriately-named attribute of the
relevant `Config` class. The latter should in term only allow to set the
attributes that have been declared previously. This enables the programmer to
have a clear overview of what configuration parameters exist by simply
inspecting the relevant `Config` class.

In the present implementation, `Config` is a subclass of the standard `dict`. To
ensure only the pre-declared attributes get put in the dictionary, the
`__setitem__()` method is extended to check the keys are declared before putting
them in the `dict`:

    def __setitem__(self, key, val):
        # check the key is permitted
        if not key in dict(self.static_keys, **self.runtime_keys, **self.section_keys):
            logging.error("Error in Config: key " + key + " not permitted.")

        # set the value in the dict
        super().__setitem__(key, val)


## Configuration files

Upon starting, the program reads the main config file `config/settings.ini` that
defines general program settings; the values are read by the instance of
`ProgramConfig` class. The main config file has to contain the following
sections and fields:

    [general]
    default_plot_dt = 
    default_hdf_dt = 
    run_name = 
    hdf_loop_delay = 
    monitoring_dt = 
    custom_command = 
    custom_device = 
    
    [run_attributes]
    
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

The `[device]` section has to contain the parameters specified in the method
`define_permitted_keys()` of the `DeviceConfig` class. The `[attributes]` are
copied verbatim into the HDF file, and displayed in the `MonitoringGUI`. Any
following config file sections specify the controls to be displayed in
`ControlGUI`.

Several types of controls are supported: `QCheckBox`, `QLineEdit`, `QComboBox`,
and `QPushButton`, etc. The exact syntax of these is subject to change, and is
best learned from the existing config files. However, the definitive guide to
what fields are required for a given control type can be obtained from the
`read_from_file()` function of the `DeviceConfig` class.

Most all devices will have a checkbox to determine whether the devices is
enabled. For example:

    [enabled]
    label = Device enabled
    type = QCheckBox
    tristate = True
    row = 0
    col = 0
    value = 2

This has to be a tristate checkbox, and the three states have the following
meanings: 1 = connect to the device, but do not read data from it; 2 = connect
to the device and read data from it; 0 = leave the device alone.

Note that config classes can also generate default options that don't need to be
specified in the `.ini` files. See `set_defaults()` methods in the `Config`
classes for examples.

For `double_connect` devices, the device driver constructor defines the data
type and shape, and when starting control, the program instantiates the driver
in order to access these parameters to correctly initialize storage. However,
for some devices it may be undesirable to instantiate the device driver twice.
For such devices, the data type and shape have to be specified in the `.ini`
file using the `dtype` and `dshape` options in the `[device]` section of

## Error handling

### Handling exceptions within a driver

If a function within a device driver has to stop due to an error condition, it
should report the error using the `logging.error()` function giving a
descriptive message of what went wrong, and return nothing:

    try:
       some code
    except SomeException as err:
       logging.error("ERROR: an error has occurred: " + str(err))
       return

If there is an abnormal condition that does not require the function to
terminate, it should be reported via the `logging.warning()` function.

Note that a driver's unhandled exceptions will likely cause the `Device`
operation to stop, unless they arise when the user or `Monitoring` call specific
device functions, as specified in the following subsection. In particular,
calling the driver's `ReadValue()` function should not cause any unhandled
exceptions to be raised unless stopping the `Device` loop is the desired effect.

### Exceptions in the main program

The exceptions that occur while calling the driver's `ReadValue()` function, or
at some other time while the driver is instantiated, are handled after the main
loop of the `Device` class, as follows:

    except Exception as err:
       warning_dict = {
               "message" : "exception in " + self.config["name"] + ": "+str(err),
               "exception" : 1,
           }
       self.warnings.append([time.time(), warning_dict])

Thus, we catch any kind of exception, package it in the `warning_dict`, and
append it to the list of warnings. Later, when `Monitoring` detects that the
list of warnings is not empty, it will read this dict, push it to InfluxDB,
report it as a `logging.warning()`, and display it in the appropriate field in
the main program GUI. Of course, such unhandled exceptions cause the device's
main loop to terminate; the warnings generated by the exception handling should
thus be taken seriously to prevent failing to record data.

If the driver raises exceptions when the `Device` instance attempts to execute
user-specified or monitoring commands, it will catch them, convert them to
strings, and report it as the return value of the command:

    try:
        ret_val = eval("device." + c.strip())
    except Exception as err:
        ret_val = str(err)

Thus, the user should not be able to crash the program, or any of its parts, by
simply trying to call inappropriate driver commands.

## Monitoring and HDF writer

While the `Device` instances collect data, `Monitoring` and `HDF_writer` are
also executing their own loops. In `Monitoring`, the loop repeatedly goes
through the following:

- Check amount of remaining free disk space
- For each `Device`:
   - Check device running and enabled
   - Check device for abnormal conditions (by reading its `dev.warnings` list)
   - Find out and display the data queue length
   - Display the last event (if any) of the device
   - Send monitoring commands
   - Obtain monitoring events and update any indicator controls
   - Get the last row of data from the `plots_queue` and format the data
   - Write data to InfluxDB
   - If writing to HDF is disabled, empty the queues (otherwise the `HDF_writer`
     will do it)
- Sleep for the loop delay

The 'monitoring events' and 'monitoring commands' referred to in the above are
used, in the present version of the program, exclusively for the so-called
`indicator` controls of a device. Each such control will cause `Monitoring` to
call a command (as specified in the device `.ini` file), and the return values
will be collected as `monitoring events`. Then, `Monitoring` updates the
`indicator`'s text and style as a function of the return value. For example, a
pump's indicator can poll the pump status, and display a green label that says
the pump is running, or a black one that says the pump is stopped.

Currently, two kinds of indicator controls are supported:

- `indicator`: a `QLabel` that changes text and style depending on the return
  values of the `monitoring_command`
- `indicator_button`: a `QPushButton` that changes its text, style, and the
  command called depending on the return values of the `monitoring_command`

Meanwhile, the `HDF_writer` instance does

- Open the specified HDF file
- For each `Device`:
   - Check device is started and has HDF writing enabled
   - Empty its `events_queue` and `data_queue` and put the data in the
     Appropriate place in the HDF file
- Sleep for the loop delay

The HDF writing is slightly different if the device is not a `slow_device`. The
fast devices collect so much data that each time the device is polled for data,
an entire dataset is returned and written as such to the HDF file. For slow
devices, we only get a couple of numbers each time, and these are appended to
the device's dataset.

## Data structure

In the HDF file, each experimental run (e.g. initial pumpdown, testing the pulse
tube cooling / heaters, etc.) is its own group. Each of these groups in turn
contains subgroups:

     /beam_source/pressure
                  thermal
                  ...

Fast devices write an entire dataset each time the device is polled. Thus, it is
recommended that they have a group for themselves. E.g. the PXIe5171 specifies
in its `.ini` config file that

    path = readout/PXIe-5171

The datasets for slow devices are normally rows of single-precision (i.e.
4-byte) floating-point datapoints, where the first column is always the UNIX
time of when the data was taken, offset by the time the run was begun. However,
the datatype of a device's dataset can be changed within the device's driver.
Indeed, the constructor should always define the data type and shape; e.g.

    self.dtype = 'f'
    self.shape = (4, )

Offsetting the UNIX time by the value stored in the `ProgramConfig`'s
`time_offset` attribute allows us to store the data as single-precision floats.
These have ~7.2 decimal digits of precision; if we want timestamps to be
specified down to 1 second of precision, a single run can be recorded for up to
~115 days. (Using double-precision floats would eliminate the need for the time
offset, but would require twice as much storage space.) The time offset is
recorded as the `time_offset` attribute of each dataset; other attributes
provide column names, units, and other additional information as relevant (e.g.,
ion gauge emission current setting).

Given that we only have one fast device (`PXIe5171`), it's driver is the best
place to learn about the data structure of fast devices. If/when other fast
devices are added, the data format is likely to change to accommodate a generic
fast device.

## Drivers

The drivers are classes inside the Python modules that are stored in `drivers/`.
Instantiating the driver class is the abstract representation of opening a
connection to a physical device. For example, many RS-232 devices have the
following lines in the class constructor:

    try:
       self.instr = self.rm.open_resource(resource_name)
    except pyvisa.errors.VisaIOError:
       # deal with the exception

The constructor also has to accomplish a few other things:

- Make the verification string, which is compared against the one specified in
  the device configuration (`.ini`) file to ensure the connection was successful

- Define what new attributes should be added to the device's dataset in the HDF
  file. If no new attributes are required, just leave it an empty list:

        self.new_attributes = []

- Specify the shape and datatype of the data returned by `ReadValue()`. For
  instance, if three float values (plus the UNIX time as a floating-point
  number) are to be returned, the correct specification would be

        self.dtype = 'f'
        self.shape = (4, )

- Define the list of warnings that will be polled at regular intervals to detect
  abnormal operation of the device. The list should probably initially be empty:

        self.warnings = []

Opening a connection to the device is of course not the only action that the
driver classes serve to provide a consistent, abstract interface to:

- Reading data works differently for each physical device in existence. Thus,
  the driver class should provide a `ReadValue()` method that implements the
  particulars about how reading data works, and should return a list of values,
  consistent with the `dtype` and `shape` of the device as specified in the
  constructor. For slow devices, the first element on the list is usually the
  time the device was polled for data.

- In order to enable using the Python [`with` statement](https://docs.python.org/3/reference/compound_stmts.html#the-with-statement), the driver has to define the methods `__enter__()` and `__exit()__`. Normally, `enter` just returns `self`, whereas `exit` does whatever cleanup is needed to close the connection to the
device:

        def __exit__(self, *exc):
            if self.instr:
                self.instr.close()

- Provide a function `GetWarnings()` that will be called at regular intervals to
  populate the list of `warnings`. This function can check for the device
  parameters are within normal ranges, or simply do nothing if appropriate.

A driver may be labelled a `meta_device` in the `.ini` file. If so, the driver's
constructor will receive a reference to the entire program as an additional
parameter. This allows writing drivers that access data from other devices. For
example, the `Watchdog` driver polls another device for some parameter, and if a
condition specified in the `.ini` file is satisfied, it will call a method from
another driver. For instance, if the beam source temperature exceeds a specified
value, the thermal watchdog can turn off the heaters --- see
`config/beam_source/thermal_watchdog.ini` for details.

### Slow and fast devices

The device `.ini` file should specify whether the device is a slow or a fast
device, e.g.

    slow_data = True

A slow device is expected to return only a few values each time its
`ReadValue()` is called, and thus requires a single dataset to contain all the
data. A fast device can return thousands or millions of datapoints each time
it is polled, together with metadata that describes this particular set of
values. Thus, the program creates a new dataset for each invocation of
`ReadValue()` of a fast device.

## Keyboard shortcuts

| Shortcut      | Action                                                       |
| ------------- | -------------------------------------------------------------|
| Ctrl+Shift+C  | show/hide all controls for a full-screen view of plots       |
| Esc           | exit full-screen view and show controls again                |
| Ctrl+P        | show/hide plots                                              |
| Ctrl+M        | show/hide monitoring info                                    |
| Ctrl+S        | start control                                                |
| Ctrl+Q        | stop control                                                 |
| Ctrl+T        | show/hide plot controls                                      |
| Ctrl+V        | switch between plots and controls vertically or side-by-side |
| Ctrl+Shift+S  | start all plots                                              |
| Ctrl+Shift+Q  | stop all plots                                               |
