import numpy as np
import time
import logging
import traceback
import sys
import importlib
import socket
import selectors
import traceback
import random
import logging
import json
import io
import struct
import threading
import pickle

class SharedData(object):
    def __init__(self, value):
        self._data = value
        self._lock = threading.Lock()

    def __get__(self, instance, owner):
        with self._lock:
            return self._data

    def __set__(self, instance, value):
        with self._lock:
            self._data = value

    def __repr__(self):
        with self._lock:
            return repr(self._data)


class StreamReceiver(threading.Thread):
    """
    Class for streaming data from red pitaya to any computer through sockets.
    Keeps the socket connection open, opening and closing for every new request
    takes too long (~4/s vs at least 100/s for a size 16e3 float array).
    Modified from https://github.com/ekbanasolutions/numpy-using-socket.
    """
    def __init__(self, address, port, obj, attr):
        threading.Thread.__init__(self)
        self._stop = threading.Event()
        self.daemon = True
        self.address = address
        self.port = port
        self.obj = obj
        self.attr = attr
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def stop(self):
        """
        Stop the streaming thread.
        """
        self._stop.set()
        self.socket.close()

    def initialize_receiver(self):
        self.socket.bind(('', self.port))
        self.socket.listen(10)
        self.conn, addr = self.socket.accept()
        self.payload_size = struct.calcsize("L")  ### CHANGED
        self.data = b''

    def receive_array(self):
        while len(self.data) < self.payload_size:
            self.data += self.conn.recv(4096)

        packed_msg_size = self.data[:self.payload_size]
        self.data = self.data[self.payload_size:]
        msg_size = struct.unpack("L", packed_msg_size)[0]

        # Retrieve all data based on message size
        while len(self.data) < msg_size:
            self.data += self.conn.recv(4096)

        frame_data = self.data[:msg_size]
        self.data = self.data[msg_size:]

        # Extract frame
        frame = pickle.loads(frame_data)
        return frame

    def run(self):
        self.obj.send('stream', f'{self.attr},{self.port}')
        self.initialize_receiver()
        while not self._stop.isSet():
            self.obj.data = self.receive_array()
        self.obj.send('stop_stream', f'{self.port}')
        self.conn.close()

class LockBoxStemlab:
    data = SharedData(None)

    def __init__(self, time_offset, conn):
        self.time_offset = time_offset

        self.hostname, self.port = conn['host'], int(conn['port'])
        self.verification_string = 'False'
        try:
            if isinstance(self.send('get', 'locked'), bool):
                self.verification_string = 'True'
        except Exception as err:
            logging.warning("LockBoxStemlab error in __init__(): "+str(err))
            self.verification_string = 'False'
            return

        self.new_attributes = []

        self.dtype = 'f'
        self.shape = (1, 2, self.send('rp', 'scope:data_length'))

        self.warnings = []

        self._acquisition = StreamReceiver(self.hostname, self.port - 1, self, 'curve')
        self._acquisition.start()
        time.sleep(1)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._acquisition.stop()
        return

    ##############################
    # CeNTREX DAQ Commands
    ##############################

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self):
        d = self.data
        timestamp = time.time()-self.time_offset
        if isinstance(d, (list, np.ndarray)):
            return [np.array([d]), [{'timestamp':timestamp}]]
        else:
            return np.nan

    ##############################
    # Commands
    ##############################

    # Ramp Commands

    def RampFrequency(self, frequency):
        self.send('set', f'ramp:frequency {frequency}')

    def GetRampFrequency(self):
        return round(self.send('rp', f'asg0:frequency'),2)

    def RampAmplitude(self, amplitude):
        self.send('set', f'ramp:amplitude {amplitude}')

    def GetRampAmplitude(self):
        return round(self.send('rp', f'asg0:amplitude'),3)

    def RampOffset(self, offset):
        self.send('set', f'ramp:offset {offset}')

    def GetRampOffset(self):
        return round(self.send('rp', f'asg0:offset'),3)

    def RampOn(self):
        self.send('set', 'locking False')

    def RampOff(self):
        self.send('set', 'locking True')

    def RampStatus(self):
        if self.send('rp', 'asg0:output_direct') == 'out1':
            return 'On'
        elif not self.get('rp', 'asg0:output_direct') == 'out1':
            return 'Off'
        else:
            return 'invalid'

    # PID commands
    def PIDSetPoint(self, setpoint):
        self.send('set', f'pid:setpoint {setpoint}')

    def GetPIDSetpoint(self):
        return round(self.send('rp', f'pid0:setpoint'), 3)

    def PIDProportional(self, proportional):
        self.send('set', f'pid:p {proportional}')

    def GetPIDProportional(self):
        return round(self.send('rp', f'pid0:proportional'),3)

    def PIDIntegral(self, integral):
        self.send('set', f'pid:i {integral}')

    def GetPIDIntegral(self):
        return round(self.send('rp', f'pid0:integral'),3)

    def PIDIVal(self, ival):
        self.send('rp', f'pid0:ival {ival}')

    def GetPIDIval(self):
        return round(self.send('rp', 'pid0:ival'),3)

    def PIDReset(self):
        self.send('rp', 'pid0:ival 0')

    def PIDFilter(self, frequency):
        self.send('set', f'pid:input_filter {frequency}')

    def GetPIDFilter(self):
        return self.send('rp', 'pid0:input_filter')

    # Scope commands
    def ScopeTrigger(self, trigger_source):
        self.send('set', f'scope:trigger_source {trigger_source}')

    def ScopeCH1Input(self, input):
        self.send('set', f'scope:input1 {input}')

    def ScopeCH2Input(self, input):
        self.send('set', f'scope:input2 {input}')

    # Lock commands

    def LockCavity(self):
        self.send('set', 'auto_relock True')
        self.send('set', 'locking True')

    def UnlockCavity(self):
        self.send('set', 'locking False')

    def LockStatus(self):
        if self.send('get', 'locked'):
            return 'Locked'
        elif not self.send('get', 'locked'):
            return 'Unlocked'
        else:
            return 'invalid'

    # Communication commands
    @staticmethod
    def _createRequest(action, value):
        return dict(
            type="text/json",
            encoding="utf-8",
            content=dict(action=action, value=value),
        )

    def send(self, action, value):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        con = sock.connect_ex((self.hostname, self.port))
        sel = selectors.DefaultSelector()
        request = self._createRequest(action, value)
        message = ClientMessage(sel, sock, (self.hostname, sock), request)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        sel.register(sock, events, data=message)

        try:
            while True:
                events = sel.select(timeout=1)
                for key, mask in events:
                    message = key.data
                    try:
                        message.process_events(mask)
                    except Exception as err:
                        logging.warning("socket warning in get: "
                                       +str(err))
                        message.close()
                # Check for a socket being monitored to continue.
                if not sel.get_map():
                    break
        except Exception as e:
            logging.warning('socket warning in get: '+str(e))
            return np.nan
        finally:
            sel.close()
            return message.result

class ClientMessage:
    """
    ClientMessage class for communication between the SocketDeviceServer and
    SocketDeviceClient classes.
    A message has the following structure:
    - fixed-lenght header
    - json header
    - content
    See https://realpython.com/python-sockets/#application-client-and-server
    for a more thorough explanation, most of the code is adapted fromt this.
    """
    def __init__(self, selector, sock, addr, request):
        self.selector = selector
        self.sock = sock
        self.addr = addr
        self.request = request
        self._recv_buffer = b""
        self._send_buffer = b""
        self._request_queued = False
        self._jsonheader_len = None
        self.jsonheader = None
        self.response = None
        self.result = np.nan

    def _set_selector_events_mask(self, mode):
        """Set selector to listen for events: mode is 'r', 'w', or 'rw'."""
        if mode == "r":
            events = selectors.EVENT_READ
        elif mode == "w":
            events = selectors.EVENT_WRITE
        elif mode == "rw":
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
        else:
            raise ValueError(f"Invalid events mask mode {repr(mode)}.")
        self.selector.modify(self.sock, events, data=self)

    def _read(self):
        try:
            # Should be ready to read
            data = self.sock.recv(4096)
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        else:
            if data:
                self._recv_buffer += data
            else:
                raise RuntimeError("Peer closed.")

    def _write(self):
        if self._send_buffer:
            try:
                # Should be ready to write
                sent = self.sock.send(self._send_buffer)
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass
            else:
                self._send_buffer = self._send_buffer[sent:]

    def _json_encode(self, obj, encoding):
        return json.dumps(obj, ensure_ascii=False).encode(encoding)

    def _json_decode(self, json_bytes, encoding):
        tiow = io.TextIOWrapper(
            io.BytesIO(json_bytes), encoding=encoding, newline=""
        )
        obj = json.load(tiow)
        tiow.close()
        return obj

    def _create_message(
        self, *, content_bytes, content_type, content_encoding
    ):
        jsonheader = {
            "byteorder": sys.byteorder,
            "content-type": content_type,
            "content-encoding": content_encoding,
            "content-length": len(content_bytes),
        }
        jsonheader_bytes = self._json_encode(jsonheader, "utf-8")
        message_hdr = struct.pack(">H", len(jsonheader_bytes))
        message = message_hdr + jsonheader_bytes + content_bytes
        return message

    def _process_response_json_content(self):
        content = self.response
        if not content.get("result") is None:
            self.result = content.get("result")
        else:
            self.result = np.nan
            raise ValueError(content.get('error'))

    def _process_response_binary_content(self):
        content = self.response
        print(f"got response: {repr(content)}")

    def process_events(self, mask):
        if mask & selectors.EVENT_READ:
            self.read()
        if mask & selectors.EVENT_WRITE:
            self.write()

    def read(self):
        self._read()

        if self._jsonheader_len is None:
            self.process_protoheader()

        if self._jsonheader_len is not None:
            if self.jsonheader is None:
                self.process_jsonheader()

        if self.jsonheader:
            if self.response is None:
                self.process_response()

    def write(self):
        if not self._request_queued:
            self.queue_request()

        self._write()

        if self._request_queued:
            if not self._send_buffer:
                # Set selector to listen for read events, we're done writing.
                self._set_selector_events_mask("r")

    def close(self):
        try:
            self.selector.unregister(self.sock)
        except Exception as e:
            logging.warning(
                f"error: selector.unregister() exception for",
                f"{self.addr}: {repr(e)}",
            )

        try:
            self.sock.close()
        except OSError as e:
            logging.warning(
                f"error: socket.close() exception for",
                f"{self.addr}: {repr(e)}",
            )
        finally:
            # Delete reference to socket object for garbage collection
            self.sock = None

    def queue_request(self):
        content = self.request["content"]
        content_type = self.request["type"]
        content_encoding = self.request["encoding"]
        if content_type == "text/json":
            req = {
                "content_bytes": self._json_encode(content, content_encoding),
                "content_type": content_type,
                "content_encoding": content_encoding,
            }
        else:
            req = {
                "content_bytes": content,
                "content_type": content_type,
                "content_encoding": content_encoding,
            }
        message = self._create_message(**req)
        self._send_buffer += message
        self._request_queued = True

    def process_protoheader(self):
        hdrlen = 2
        if len(self._recv_buffer) >= hdrlen:
            self._jsonheader_len = struct.unpack(
                ">H", self._recv_buffer[:hdrlen]
            )[0]
            self._recv_buffer = self._recv_buffer[hdrlen:]

    def process_jsonheader(self):
        hdrlen = self._jsonheader_len
        if len(self._recv_buffer) >= hdrlen:
            self.jsonheader = self._json_decode(
                self._recv_buffer[:hdrlen], "utf-8"
            )
            self._recv_buffer = self._recv_buffer[hdrlen:]
            for reqhdr in (
                "byteorder",
                "content-length",
                "content-type",
                "content-encoding",
            ):
                if reqhdr not in self.jsonheader:
                    raise ValueError(f'Missing required header "{reqhdr}".')

    def process_response(self):
        content_len = self.jsonheader["content-length"]
        if not len(self._recv_buffer) >= content_len:
            return
        data = self._recv_buffer[:content_len]
        self._recv_buffer = self._recv_buffer[content_len:]
        if self.jsonheader["content-type"] == "text/json":
            encoding = self.jsonheader["content-encoding"]
            self.response = self._json_decode(data, encoding)
            self._process_response_json_content()
        else:
            # Binary or unknown content-type
            self.response = data
            self._process_response_binary_content()
        # Close when response has been processed
        self.close()
