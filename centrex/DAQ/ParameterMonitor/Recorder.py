import threading
import time
import csv
import pyvisa

class Recorder(threading.Thread):
    def __init__(self, current_run_dir, path, driver, COM_port, dev_name, dt, attrs):
        # thread control
        threading.Thread.__init__(self)
        self.active = threading.Event()

        # record operating parameters
        self.dir = current_run_dir + "/" + path
        self.driver = driver
        self.COM_port = COM_port
        self.dev_name = dev_name
        self.dt = dt
        self.time_offset = time.time()
        with open(self.dir+"/"+self.dev_name+"_params.csv",'w') as params_f:
            dev_params = csv.writer(params_f)
            dev_params.writerow(["time_offset", self.time_offset])
            for key in attrs:
                dev_params.writerow([key, attrs[key]])

    def verify_operation(self):
        rm = pyvisa.ResourceManager()
        with self.driver(rm, self.COM_port) as device: 
            return device.VerifyOperation()

    # main recording loop
    def run(self):
        rm = pyvisa.ResourceManager()
        with open(self.dir+"/"+self.dev_name+".csv",'a',1) as CSV_f,\
                self.driver(rm, self.COM_port) as device: 
            dev_dset = csv.writer(CSV_f)
            while self.active.is_set():
                dev_dset.writerow([ time.time() - self.time_offset] + device.ReadValue() )
                time.sleep(self.dt)
