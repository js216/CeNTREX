import time
import logging
import subprocess
import numpy as np

class ClockSync:
    """
    Driver to periodically sync the system time clock with the specified NTP
    server.
    Requires psexec to be present in the path of the Windows computer
    (simply download PSTools and copy psexec to the Drive:\Windows folder).
    The windows time service (w32tm) must be running for this clock sync to work.
    """
    def __init__(self, time_offset, user, password):
        self.time_offset = time_offset
        self.user = user
        self.password = password

        self.dtype = ('f4',)
        self.shape = (2,)

        self.nr_peers, self.peer = self.GetPeer()
        if np.isnan(self.nr_peers):
            self.verification_string = "False"
            return
        elif self.nr_peers < 1:
            self.verification_string = "False"
            return
        else:
            self.verification_string = "True"

        self.warnings = []
        self.new_attributes = [("#peers", f"{self.nr_peers}"),
                               ("peer", f"{self.peer}")]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return

    #######################################################
    # CeNTREX DAQ Commands
    #######################################################


    def CreateWarning(self, warning):
        warning_dict = { "message" : warning}
        self.warnings.append([time.time(), warning_dict])

    def GetWarnings(self):
        return []

    def ReadValue(self):
        # process = subprocess.run(f'w32tm /stripchart /computer:{self.peer} /samples:1',
        #                          stdout = subprocess.PIPE,
        #                          stderr = subprocess.PIPE)
        # try:
        #     delay_before = float(process.stdout.decode().split('\n')[3].split('o:')[1].split('s')[0])
        # except:
        #     delay_before = np.nan
        # self.SyncTime()
        process = subprocess.run(f'w32tm /stripchart /computer:{self.peer} /samples:1',
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE)
        try:
            delay_after = float(process.stdout.decode().split('\n')[3].split('o:')[1].split('s')[0])
        except:
            delay_after = np.nan
        return [time.time() - self.time_offset, delay_after]

    #######################################################
    # Device Commands
    #######################################################

    def SyncTime(self):
        cmd = f"psexec -u {self.user} -p {self.password} w32tm /resync"
        process = subprocess.Popen(cmd, stdout = subprocess.PIPE,
                                   stderr = subprocess.PIPE)
        if process.returncode == 0:
            return
        elif process.returncode == 1326:
            logging.error("ClockSync error in SyncTime : username or password incorrect")
            self.warnings.append("ClockSync: username or password incorrect")

    def GetPeer(self):
        process = subprocess.run('w32tm /query /peers',
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE)
        stdout = process.stdout.decode().split('\n')
        if stdout[0][:6] == '#Peers':
            nr_peers = int(stdout[0][-1])
        else:
            nr_peers = np.nan
        if stdout[2][:5] == 'Peer:':
            peer = stdout[2][6:].split(',')[0]
        else:
            peer = np.nan
        return nr_peers, peer
