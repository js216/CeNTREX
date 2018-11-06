import threading
import time
import csv

class Recorder(threading.Thread):
    def __init__(self, rm, current_run_dir, path, driver, COM_port, dev_name, dt, attrs):
        # thread control
        threading.Thread.__init__(self)
        self.active = threading.Event()
        self.active.set()

        # record operating parameters
        self.rm = rm
        self.dir = current_run_dir + "/" + path
        self.driver = driver
        self.COM_port = COM_port
        self.dev_name = dev_name
        self.dt = dt
        with open(self.dir+"/"+self.dev_name+"_params.csv",'w') as params_f:
            dev_params = csv.writer(params_f)
            for key in attrs:
                dev_params.writerow([key, attrs[key]])

        # select and record time offset
        self.time_offset = time.time()
        with open(self.dir+"/"+self.dev_name+"_time_offset.csv",'w') as to_f:
            to_f.write(str(self.time_offset))

    # main recording loop
    def run(self):
        with open(self.dir+"/"+self.dev_name+".csv",'a',1) as CSV_f,\
                self.driver(self.rm, self.COM_port) as device: 
            dev_dset = csv.writer(CSV_f)
            while self.active.is_set():
                dev_dset.writerow([ time.time() - self.time_offset,
                                    device.ReadValue() ])
                time.sleep(self.dt)
