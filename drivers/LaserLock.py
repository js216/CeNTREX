import io
import json
import logging
import selectors
import socket
import struct
import sys
import time

import numpy as np

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
    for a more thorough explanation, most of the code is adapted from this.
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
        tiow = io.TextIOWrapper(io.BytesIO(json_bytes), encoding=encoding, newline="")
        obj = json.load(tiow)
        tiow.close()
        return obj

    def _create_message(self, *, content_bytes, content_type, content_encoding):
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
            raise ValueError(content.get("error"))

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
                "error: selector.unregister() exception for",
                f"{self.addr}: {repr(e)}",
            )

        try:
            self.sock.close()
        except OSError as e:
            logging.warning(
                "error: socket.close() exception for",
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
            self._jsonheader_len = struct.unpack(">H", self._recv_buffer[:hdrlen])[0]
            self._recv_buffer = self._recv_buffer[hdrlen:]

    def process_jsonheader(self):
        hdrlen = self._jsonheader_len
        if len(self._recv_buffer) >= hdrlen:
            self.jsonheader = self._json_decode(self._recv_buffer[:hdrlen], "utf-8")
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


class LaserLock:
    """
    Driver to connect to laser locking on different computer via socket
    communication
    """

    def __init__(self, time_offset, socket_connection):
        self.time_offset = time_offset
        self.host = socket_connection["host"]
        self.port = int(socket_connection["port"])
        self.device_name = "Laser Lock"

        self.dtype = (
            "f",
            "bool",
            "f8",
            "f8",
            "bool",
            "bool",
            "f",
            "f",
            "f8",
            "f8",
            "f8",
            "f8",
            "f8",
            "f8",
        )
        self.shape = (11,)

        self.new_attributes = []

        self.warnings = []

        try:
            self.verification_string = self.request("query", "verification")
        except Exception:
            self.verification_string = "False"

    def __exit__(self, *exc):
        return

    def __enter__(self):
        return self

    def ReadValue(self):
        values = self.request("query", "ReadValue")
        t = time.time() - self.time_offset
        try:
            if np.isnan(values):
                return np.nan
        except Exception:
            values = [v if not isinstance(v, type(None)) else np.nan for v in values]
            return [t] + values

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def set_lockpoint_laser_1(self, lockpoint: float):
        self.set_lockpoint(0, lockpoint)

    def set_lockpoint_laser_2(self, lockpoint: float):
        self.set_lockpoint(1, lockpoint)

    def move_frequency_laser_1(self, frequency_deviation: float):
        self.move_frequency(0, frequency_deviation)

    def move_frequency_laser_2(self, frequency_deviation: float):
        self.move_frequency(1, frequency_deviation)

    def move_frequency(self, laser: int, frequency_deviation: float):
        cmd = f"lasers[{laser}].move_frequency({frequency_deviation})"
        _ = self.request("command", cmd)

    def set_lockpoint(self, laser: int, lockpoint: float):
        cmd = f"set_laser_lockpoint({lockpoint},{laser})"
        _ = self.request("command", cmd)

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
        _ = sock.connect_ex((self.host, self.port))
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
                        logging.warning(
                            "{0} socket warning in request: ".format(self.device_name)
                            + str(err)
                        )
                        message.close()
                # Check for a socket being monitored to continue.
                if not sel.get_map():
                    break
        except Exception as e:
            logging.warning(
                "{0} socket warning in request: ".format(self.device_name) + str(e)
            )
            warning_dict = {"message": str(e)}
            self.warnings.append([time.time(), warning_dict])
            return np.nan
        finally:
            sel.close()
            return message.result
