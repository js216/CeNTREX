import threading

class Device(threading.Thread):
    def __init__(self, config):
        self.active = threading.Event()
        self.active.clear()
        self.config = config
        self.commands = []
        self.operational = False

    def setup_connection(self):
        threading.Thread.__init__(self)
        self.rm = pyvisa.ResourceManager()

        # check the directory for CSV files exists, else create it
        self.CSV_dir = self.config["current_run_dir"]+"/"+self.config["path"]
        if not os.path.isdir(self.CSV_dir):
            try:
                os.mkdir(self.CSV_dir)
            except OSError:
                return

        # select and record the time offset
        self.config["time_offset"] = time.time()
        to_fname = self.CSV_dir+"/"+self.config["name"]+"_time_offset.csv"
        with open(to_fname,'w') as to_f:
            to_f.write(str(self.config["time_offset"]))

        # verify the device responds correctly
        constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]
        with self.config["driver"](self.rm, *constr_params) as dev: 
            if dev.verification_string == self.config["correct_response"]:
                self.operational = True
            else:
                self.operational = False

        self.rm.close()

    def run(self):
        # check connection to the device was successful
        if not self.operational:
            return

        # open CSV files
        CSV_fname = self.CSV_dir+"/"+self.config["name"]+".csv"
        events_fname = self.CSV_dir+"/"+self.config["name"]+"_events.csv"
        with open(CSV_fname,'a',1) as CSV_f,\
             open(events_fname,'a',1) as events_f:
            dev_dset = csv.writer(CSV_f)
            events_dset = csv.writer(events_f)
            constr_params = [self.config["controls"][cp]["var"].get() for cp in self.config["constr_params"]]

            # main control loop
            self.rm = pyvisa.ResourceManager()
            with self.config["driver"](self.rm, *constr_params) as device: 
                while self.active.is_set():
                    # record numerical values
                    try:
                        dev_dset.writerow( [time.time() - self.config["time_offset"]] + device.ReadValue() )
                    except ValueError as err:
                        ret_val = str(err)
                        ret_val = "None" if not ret_val else ret_val
                        events_dset.writerow([ time.time()-self.config["time_offset"], ret_val ])

                    # send control commands, if any, to the device, and record return values
                    for c in self.commands:
                        try:
                            ret_val = eval("device." + c)
                        except (ValueError, AttributeError) as err:
                            ret_val = str(err)
                        ret_val = "None" if not ret_val else ret_val
                        events_dset.writerow([ time.time()-self.config["time_offset"], c, ret_val ])
                    self.commands = []

                    # loop delay
                    try:
                        time.sleep(float(self.config["controls"]["dt"]["var"].get()))
                    except ValueError:
                        time.sleep(1)
