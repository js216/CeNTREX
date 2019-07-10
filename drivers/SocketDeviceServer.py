import importlib
import sys
import socket
import selectors
import traceback
import threading
from collections import deque
import random
import logging
import time
from types import FunctionType
import functools
import json
import io
import struct
import inspect
from queue import Queue
import numpy as np

#############################################
# Class for server side messages
#############################################

class ServerMessage:
    """
    ServerMessage class for communication between the SocketDeviceServer and
    SocketDeviceClient classes.
    A message has the following structure:
    - fixed-lenght header
    - json header
    - content
    See https://realpython.com/python-sockets/#application-client-and-server
    for a more thorough explanation, most of the code is adapted from this.
    """
    def __init__(self, selector, sock, addr, data, commands, timeout):
        self.selector = selector
        self.sock = sock
        self.addr = addr
        self._recv_buffer = b""
        self._send_buffer = b""
        self._jsonheader_len = None
        self.jsonheader = None
        self.request = None
        self.response_created = False

        self.data = data
        self.commands = commands
        self.timeout = timeout

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
                # Close when the buffer is drained. The response has been sent.
                if sent and not self._send_buffer:
                    self.close()

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

    def _create_response_json_content(self):
        action = self.request.get("action")
        if action == "query":
            query = self.request.get("value")
            if self.data.get(query):
                content = {"result": self.data.get(query)}
            else:
                content = {"error": f'No match for "{query}".'}
        elif action == "command":
            command = self.request.get("value")
            tstart = time.time()
            self.commands.put(command)
            while True:
                if self.data["commandReturn"].get(command):
                    content = {"result": self.data["commandReturn"].get(command)}
                    del self.data["commandReturn"][command]
                    break
                # manual timeout if it takes to long to execute command
                # subsequently returns to the client a message stating function
                # execution took too much time
                elif time.time() - tstart > self.timeout:
                    content = {"result": (time.time(), command, "not executed, {0}s timeout".format(self.timeout))}
                    break
        else:
            content = {"error": f'invalid action "{action}".'}
        content_encoding = "utf-8"
        response = {
            "content_bytes": self._json_encode(content, content_encoding),
            "content_type": "text/json",
            "content_encoding": content_encoding,
        }
        return response

    def _create_response_binary_content(self):
        response = {
            "content_bytes": b"First 10 bytes of request: "
            + self.request[:10],
            "content_type": "binary/custom-server-binary-type",
            "content_encoding": "binary",
        }
        return response

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
            if self.request is None:
                self.process_request()

    def write(self):
        if self.request:
            if not self.response_created:
                self.create_response()

        self._write()

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

    def process_request(self):
        content_len = self.jsonheader["content-length"]
        if not len(self._recv_buffer) >= content_len:
            return
        data = self._recv_buffer[:content_len]
        self._recv_buffer = self._recv_buffer[content_len:]
        if self.jsonheader["content-type"] == "text/json":
            encoding = self.jsonheader["content-encoding"]
            self.request = self._json_decode(data, encoding)
        else:
            # Binary or unknown content-type
            self.request = data
        # Set selector to listen for write events, we're done reading.
        self._set_selector_events_mask("w")

    def create_response(self):
        if self.jsonheader["content-type"] == "text/json":
            response = self._create_response_json_content()
        else:
            # Binary or unknown content-type
            response = self._create_response_binary_content()
        message = self._create_message(**response)
        self.response_created = True
        self._send_buffer += message

#############################################
# Socket Server Class
#############################################

class socketServer(threading.Thread):
    """
    Handles communication with external clients in a separate thread.
    """
    def __init__(self, device, host, port, timeout):
        threading.Thread.__init__(self)
        self.device = device
        self.host = ''
        self.timeout = float(timeout)
        self.port = int(port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen()
        self.sock.setblocking(False)
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.sock, selectors.EVENT_READ, data=None)

        self.active = threading.Event()
        self.active.clear()

    def accept_wrapper(self, sock):
        conn, addr = sock.accept()  # Should be ready to read
        logging.info("{0} accepted connection from".format(self.device.device_name), addr)
        conn.setblocking(False)
        message = ServerMessage(self.sel, conn, addr, self.device.data,
                                self.device.commands, self.timeout)
        self.sel.register(conn, selectors.EVENT_READ, data=message)

    def run(self):
        self.active.set()
        while self.active.is_set():
            events = self.sel.select(timeout = self.timeout)
            for key, mask in events:
                if key.data is None:
                    self.accept_wrapper(key.fileobj)
                else:
                    message = key.data
                    try:
                        message.process_events(mask)
                    except Exception as err:
                        logging.warning("{2} socket warning for "
                                       +"{0}:{1} : ".format(self.host, self.port, self.device.device_name)
                                       +str(err))
                        message.close()

#############################################
# Execute Commands Class
#############################################

class executeCommands(threading.Thread):
    """
    Handles executing commands from external clients in a separate thread.
    """
    def __init__(self, device):
        threading.Thread.__init__(self)
        self.device = device
        self.commands = device.commands
        self.data = device.data

        self.active = threading.Event()
        self.active.clear()

    def run(self):
        self.active.set()
        while self.active.is_set():
            # check if any new commands
            if not self.commands.empty():
                c = self.commands.get()
                try:
                    # try to execute the command
                    value = eval('self.device.'+c.strip())
                    # storing command in the server device database
                    self.data['commandReturn'][c] = (time.time(), c, value)
                except Exception as e:
                    self.data['commandReturn'][c] = (time.time(), c, 'Exception: '+str(e))
                    pass
            time.sleep(5e-3)

#############################################
# Socket Device Server Class
#############################################

def wrapperReadValueServerMethod(func):
    """
    Wraps the ReadValue method of a device driver.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        command = 'ReadValueServer'
        args[0].commands.put(command)
        while True:
            if args[0].data["commandReturn"].get(command):
                readvalue = args[0].data["commandReturn"].get(command)
                print(readvalue)
                if 'Exception' in readvalue[2]:
                    return np.nan
                args[0].data[command] = (readvalue[0], readvalue[2])
                del args[0].data["commandReturn"][command]
                break
        return readvalue[2]
    return wrapper

def ServerClassDecorator(cls):
    """
    Decorator for the SocketDeviceServerClass to modify driver functions for use
    with a socket server.
    """
    for attr_name in dir(cls):
        attr_value = getattr(cls, attr_name)
        if isinstance(attr_value, FunctionType):
            if attr_name == 'ReadValue':
                attribute = wrapperReadValueServerMethod(attr_value)
                setattr(cls, 'ReadValueServer', attribute)
            elif attr_name in ['__init__', 'accept_wrapper', 'run_server', '__enter__', '__exit__']:
                continue
            elif not inspect.signature(attr_value).parameters.get('self'):
                # don't wrap static methods, very clunky method but couldn't
                # figure out a better way
                continue
            else:
                continue
                # attribute = wrapperSocketServerMethods(attr_value)
                # setattr(cls, attr_name, attribute)
    return cls

def SocketDeviceServer(*args):
    """
    Function returns the SocketDeviceServer class which functions as a driver.
    Need to do it this way because the parent class is a driver class, dynamically
    loaded when the SocketDeviceServer function is called from the main DAQ
    software.
    """
    driver = args[2]
    driver_spec = importlib.util.spec_from_file_location(
            driver,
            "drivers/" + driver + ".py",
        )
    driver_module = importlib.util.module_from_spec(driver_spec)
    driver_spec.loader.exec_module(driver_module)
    driver = getattr(driver_module, driver)

    @ServerClassDecorator
    class SocketDeviceServerClass(driver):
        """
        SocketDeviceServer template class for easy setup of specific device classes
        """
        def __init__(self, time_offset, port, device_name, timeout, *device_args):
            self.device_name = device_name
            # initializing the server device database
            self.verification_string = 'False'
            self.data = {'ReadValue':np.nan, 'verification':self.verification_string,
                         'commandReturn':{}}

            # server commands queue for storing commands of external clients
            self.commands = Queue()

            # start thread responsible for executing commands from external
            # clients
            self.thread_device = executeCommands(self)
            self.thread_device.start()

            # initialize the device driver
            driver.__init__(self, time_offset, *device_args)
            # add verification string to the server device database
            self.data['verification'] = self.verification_string

            # starting the thread responsible for handling communication with
            # external clients
            self.thread_server = socketServer(self, '', int(port), float(timeout))
            self.thread_server.start()
            # sleeping for the same amount of time as the server communication
            # timeout to prevent problems when initializing the class twice
            # in the main DAQ software
            time.sleep(float(timeout))

        def __exit__(self, *exc):
            """
            Properly stopping the communication and command execution threads.
            """
            self.thread_device.active.clear()
            self.thread_server.active.clear()
            super(SocketDeviceServerClass, self).__exit__(*exc)

    return SocketDeviceServerClass(*args)
