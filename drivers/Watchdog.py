import numpy as np
import time
import logging

def split(string, separator=","):
    return [x.strip() for x in string.split(separator)]

class Watchdog:
    def __init__(self, parent, time_offset, *params):
        self.parent = parent
        self.time_offset = time_offset
        self.dev1, self.param1, self.comp1, self.number1, self.dev2, self.function, self.message = params
        self.watchdog_active = True

        # convert numbers from str to float
        try:
            self.number1 = float(self.number1)
        except Exception as err:
            logging.error("Error in Watchdog __init__(): cannot convert value to float: " + str(self.number1))

        # make the verification string
        self.verification_string = "N/A"

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (0, )

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def ReadValue(self):
        if self.watchdog_active:
            self.CheckConditions()

    def CheckConditions(self):
        # get the latest row of data
        try:
            latest_data = self.parent.devices[self.dev1].config["plots_queue"][-1]
        except IndexError:
            return

        # extract the desired parameter 1
        col_names = split(self.parent.devices[self.dev1].config["attributes"]["column_names"])
        try:
            param1_val = latest_data[col_names.index(self.param1)]
        except IndexError:
            logging.error("Error in Watchdog: param not found: " + self.param1)
            return

        # convert the parameters to number
        try:
            param1_num = float(param1_val)
        except Exception as err:
            logging.error("Error in Watchdog: cannot convert value to float: " + str(param1_val))
            return

        # get the correct comparisons
        if self.comp1 == "is greater than":
            comp1 = param1_num.__gt__(self.number1)
        elif self.comp1 == "is equal to":
            comp1 = param1_num.__eq__(self.number1)
        elif self.comp1 == "is less than":
            comp1 = param1_num.__lt__(self.number1)
        
        # check the parameter is not outside the specified range
        if comp1:
            self.ManageCondition()

    def ManageCondition(self):
        # raise a warning
        warning_dict = {"message" : self.message}
        self.warnings.append([time.time(), warning_dict])
        logging.warning("warning in Watchdog: " + str(warning_dict))

        # handle the situation
        self.parent.devices[self.dev2].commands.append(self.function)

    def EnableWatchdog(self):
        self.watchdog_active = True

    def DisableWatchdog(self):
        self.watchdog_active = False
