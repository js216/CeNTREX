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
import numpy as np
import inspect
import functools
import time
from types import FunctionType

#############################################
# Class for client side messages
#############################################

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
        if content.get("result"):
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

#############################################
# Socket Device Client Class
#############################################

def wrapperSocketClientMethods(func):
    """
    Function wrapper for all methods of the device driver class excluding static
    methods, __**__ methods and ReadValue.
    Wraps device driver methods to function with the socket client.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        device_name = args[0].device_name
        value = args[0].request("command", func.__name__+'(*{0}, **{1})'.format(args[1:], kwargs))
        try:
            if np.isnan(value):
                logging.warning("SocketClient warning in {0}: cannot connect to server".format(func.__name__))
                return np.nan
        except Exception:
            pass
        if func.__name__ not in  value[1]:
            logging.warning("{1} socket warning in {0}: wrong function return".format(func.__name__, device_name))
            return np.nan
        elif isinstance(value[2], type(None)):
            # some functions return None, such as GetWarnings, then the strings
            # search will fail
            return value[2]
        elif "not executed" in value[2]:
            logging.warning("{2} socket warning in {0}: {1}".format(func.__name__, value[2], device_name))
            return np.nan
        elif "Exception" in value[2]:
            logging.warning("{2} socket warning in {0}: {1}".format(func.__name__, value[2], device_name))
            return np.nan
        return value[2]
    return wrapper

def wrapperReadValueClientMethod(func):
    """
    Function wrapper for the ReadValue method of the device driver class to
    ensure compatibility with the socket client
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        value = args[0].request("query", "ReadValue")
        try:
            if np.isnan(value):
                return np.nan
        except:
            # corrects time with time_offset of the client system, assumes clocks
            # are synchronized between systems with minimal offsets
            v = [value[0]-args[0].time_offset]
            # uses client system time as timestamp, assuming no/insignificant delay
            # between grabbing data from server and client receiving data.
            # v = [time.time()-args[0].time_offset]
            v.extend(value[1])
            return v
    return wrapper

def wrapperGetWarningsClientMethod(func):
    """
    Function wrapper for the GetWarnings method of the device drier class to
    ensure warnings are only recorded on the server side, since GetWarnings
    clears the existing warnings, so all warnings would be scattered among
    clients and server.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return None
    return wrapper

def ClientClassDecorator(cls):
    """
    Decorator for the SocketDeviceClientClass to modify driver function for use
    with the socket client.
    """
    for attr_name in dir(cls):
        attr_value = getattr(cls, attr_name)
        if isinstance(attr_value, FunctionType):
            if attr_name == 'ReadValue':
                attribute = wrapperReadValueClientMethod(attr_value)
                setattr(cls, attr_name, attribute)
            elif attr_name == 'GetWarnings':
                attribute = wrapperGetWarningsClientMethod(attr_value)
                setattr(cls, attr_name, attribute)
            elif attr_name in ['__init__', '_createRequest', 'request', '__enter__', '__exit__']:
                continue
            elif not inspect.signature(attr_value).parameters.get('self'):
                # don't wrap static methods, very clunky method but couldn't
                # figure out a better way
                continue
            else:
                attribute = wrapperSocketClientMethods(attr_value)
                setattr(cls, attr_name, attribute)
    return cls

def SocketDeviceClient(*args):
    """
    Function returns the SocketDeviceClient class which functions as a driver.
    Need to do it this way because the parent class is a driver class, dynamically
    loaded when the SocketDeviceClient function is called from the main DAQ
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

    @ClientClassDecorator
    class SocketDeviceClientClass(driver):
        """
        SocketDeviceClient template class for easy setup of specific device classes
        """
        def __init__(self, time_offset, socket_connection, device_name, *device_args):
            self.device_name = device_name
            device_args = [eval(_) for _ in device_args]
            self.host = socket_connection['host']
            self.port = int(socket_connection['port'])
            driver.__init__(self, time_offset, *device_args)

        def __exit__(self, *exc):
            try:
                driver.__exitclient__(self, *exc)
                return
            except:
                return

        def _createRequest(self, action, value):
            return dict(
                type="text/json",
                encoding="utf-8",
                content=dict(action=action, value=value),
            )

        def request(self, action, value):
            """
            Send a request to the SocketDeviceServer
            """
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            con = sock.connect_ex((self.host, self.port))
            sel = selectors.DefaultSelector()
            request = self._createRequest(action, value)
            message = ClientMessage(sel, sock, (self.host, sock), request)
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
                            logging.warning("{0} socket warning in request: ".format(self.device_name)
                                           +str(err))
                            message.close()
                    # Check for a socket being monitored to continue.
                    if not sel.get_map():
                        break
            except Exception as e:
                logging.warning('{0} socket warning in request: '.format(self.device_name)+str(e))
                return np.nan
            finally:
                sel.close()
                return message.result

    return SocketDeviceClientClass(*args)
