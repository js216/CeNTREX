import functools
import importlib
import inspect
import json
import logging
import threading
import time
from pathlib import Path
from types import FunctionType

import numpy as np
import zmq
import zmq.auth
from zmq.auth.thread import ThreadAuthenticator


def wrapperNetworkClientMethods(func):
    """
    Function wrapper for all methods not rewritten in NetworkingClientClass and
    excluding static methods
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        func.__name__ + "(*{0}, **{1})".format(args[1:], kwargs)
        retval = self.ExecuteNetworkCommand(
            func.__name__ + "(*{0}, **{1})".format(args[1:], kwargs)
        )
        return retval

    return wrapper


def NetworkingClassDecorator(cls):
    """
    Decorator for the NetworkingClientClass to modify driver function for use
    with the socket client.
    """
    # don't wrap methods with this name
    ignore = [
        "__init__",
        "__enter__",
        "__exit__",
        "OpenConnection",
        "CloseConnection",
        "ExecuteNetworkCommand",
        "ReadValue",
        "Decode",
        "GetWarnings",
    ]
    for attr_name in dir(cls):
        attr_value = getattr(cls, attr_name)
        if isinstance(attr_value, FunctionType):
            if attr_name in ignore:
                continue
            elif not inspect.signature(attr_value).parameters.get("self"):
                # don't wrap static methods, very clunky method but couldn't
                # figure out a better way
                continue
            else:
                attribute = wrapperNetworkClientMethods(attr_value)
                setattr(cls, attr_name, attribute)
    return cls


class ReadValueThread(threading.Thread):
    def __init__(self, parent):
        super(ReadValueThread, self).__init__()
        self.parent = parent
        self.value = None
        self.daemon = True
        self.active = threading.Event()
        self.finished = False

    def run(self):
        """
        Keep listening on the readout port for new messages from the
        server in a separate thread, such that the parent class can issue
        control commands while waiting for a message.
        """
        while self.active.is_set():
            # wrap in try-except because the context is sometimes terminated
            # upon stopping the program before the while loop reaches the
            # cleared thread event active
            try:
                data = self.parent.socket_readout.recv_string()
                retval = self.parent.Decode(data)
                retval[0] -= self.parent.time_offset
                self.value = retval
                # need a sleep to release to other threads
                time.sleep(1e-4)
            except zmq.error.ContextTerminated:
                warning_dict = {
                    "message": "stopped ReadValueThread because context was terminated"
                }
                self.parent.warnings.append([time.time(), warning_dict])
                logging.info(
                    f"{self.parent.device_name} networking info in "
                    + f"ReadValueThread : stopped subscription"
                )
                pass
            self.finished = True


def NetworkingClient(time_offset, driver, connection, *args):
    # if connection is passed as a string, convert it to a dictionary
    if isinstance(connection, str):
        connection = json.loads(connection)

    # very hacky way to get shape and dtype from the original driver
    # this is defined in __init__ of the driver and as such you need to
    # initialize the class to access it, which throws exceptions for some
    # drivers if a usb/serial/whatever device is not attached
    with open(f"drivers/{driver}.py") as f:
        text = f.readlines()

    driver_spec = importlib.util.spec_from_file_location(
        driver,
        "drivers/" + driver + ".py",
    )

    driver_module = importlib.util.module_from_spec(driver_spec)
    driver_spec.loader.exec_module(driver_module)
    driver = getattr(driver_module, driver)

    @NetworkingClassDecorator
    class NetworkingClientClass(driver):
        def __init__(self, time_offset, connection, *args):
            logging.info(f"Initializing NetworkingClientClass({str(driver)})")
            self.time_offset = time_offset

            self.server = connection["server"]
            self.port_readout = connection["port_readout"]
            self.port_control = connection["port_control"]
            self.publisher = connection["publisher_name"]
            self.device_name = connection["device_name"]

            # set the control connection timeout
            self.timeout = 10e3
            # open connections to the server
            self.topicfilter = f"{self.publisher}-{self.device_name}"
            self.OpenConnection()

            self.warnings = []

            self.readvalue_thread = ReadValueThread(self)
            self.readvalue_thread.active.set()
            self.readvalue_thread.start()

            self.verification_string = self.ExecuteNetworkCommand("verification_string")
            logging.info(
                f"NetworkingClientClass: retrieved verification_string {self.verification_string}"
            )

            self.dtype = self.ExecuteNetworkCommand("dtype")
            logging.info(f"NetworkingClientClass: retrieved dtype {self.dtype}")

            self.shape = self.ExecuteNetworkCommand("shape")
            logging.info(f"NetworkingClientClass: retrieved shape {self.shape}")

            self.new_attributes = []

            self.is_networking_client = True
            logging.info(f"NetworkingClientClass: finished __init__")

        def __exit__(self, *args):
            self.readvalue_thread.active.clear()
            while not self.readvalue_thread.finished:
                time.sleep(1e-3)
            self.socket_readout.setsockopt(zmq.LINGER, 0)
            self.socket_control.setsockopt(zmq.LINGER, 0)
            self.socket_readout.close()
            self.socket_control.close()
            self.context.term()

        def GetWarnings(self):
            warnings = self.warnings.copy()
            self.warnings = []
            return warnings

        def OpenConnection(self):
            # starting the context
            self.context = zmq.Context()

            # opening the sockets
            self.socket_control = self.context.socket(zmq.REQ)
            self.socket_readout = self.context.socket(zmq.SUB)

            # loading authentication keys
            file_path = Path(__file__).resolve()
            public_keys_dir = file_path.parent.parent / "authentication" / "public_keys"
            secret_keys_dir = (
                file_path.parent.parent / "authentication" / "private_keys"
            )
            server_public_file = public_keys_dir / "server.key"
            client_secret_file = secret_keys_dir / "client.key_secret"

            server_public, _ = zmq.auth.load_certificate(str(server_public_file))
            client_public, client_secret = zmq.auth.load_certificate(
                str(client_secret_file)
            )

            self.socket_control.curve_secretkey = client_secret
            self.socket_control.curve_publickey = client_public
            self.socket_control.curve_serverkey = server_public

            # starting readout
            self.socket_readout.setsockopt_string(zmq.SUBSCRIBE, self.topicfilter)
            self.socket_readout.connect(f"tcp://{self.server}:{self.port_readout}")
            logging.info("NetworkingClientClass: connected to readout socket")

            # starting control
            self.socket_control.connect(f"tcp://{self.server}:{self.port_control}")
            logging.info("NetworkingClientClass: connected to control socket")

            logging.info("NetworkingClientClass: connection opened")

        def CloseConnection(self):
            # close all connections
            self.readvalue_thread.active.clear()
            while not self.readvalue_thread.finished:
                time.sleep(1e-3)
            self.socket_readout.setsockopt(zmq.LINGER, 0)
            self.socket_control.setsockopt(zmq.LINGER, 0)
            self.socket_readout.close()
            self.socket_control.close()
            self.context.term()

        def Decode(self, message):
            """
            Function decodes the message received from the publisher into a
            topic and python object via json serialization
            """
            dat = message[len(self.topicfilter) :]
            retval = json.loads(dat)
            return retval

        def ExecuteNetworkCommand(self, command):
            # send command to the server hosting the device
            self.socket_control.send_json([self.device_name, command])
            logging.info(
                f"ExecuteNetworkCommand : {command} to {self.device_name} at {self.server}:{self.port_control}"
            )

            # need the timeout because REP-REQ will wait indefinitely for a
            # reply, need to handle when a server stops or a message isn't
            # received for some other reason
            if (self.socket_control.poll(self.timeout) & zmq.POLLIN) != 0:
                status, retval = self.socket_control.recv_json()
                if status == "OK":
                    return retval
                else:
                    logging.warning(
                        f"{self.device_name} networking warning in "
                        + f"ExecuteNetworkCommand : error for {command} -> {retval}"
                    )
                    return np.nan

            # error handling if no reply received withing timeout
            logging.warning(
                f"{self.device_name} networking warning in ExecuteNetworkCommand : no response from server"
            )
            warning_dict = {
                f"message": "ExecuteNetworkCommand for {device_name}: no response from server"
            }
            self.warnings.append([time.time(), warning_dict])
            self.socket_control.setsockopt(zmq.LINGER, 0)
            self.socket_control.close()
            self.socket_control = self.context.socket(zmq.REQ)
            self.socket_control.connect(f"tcp://{self.server}:{self.port_control}")
            return np.nan

        def ReadValue(self):
            if self.readvalue_thread.value:
                value = self.readvalue_thread.value
                self.readvalue_thread.value = None
                return value
            else:
                return np.nan

    return NetworkingClientClass(time_offset, connection, *args)


# navigate to /authentication folder
# ip = "10.10.222.9"
# port = 12346
# name = "SynthHD Pro"
# import zmq
# import zmq.auth
# context = zmq.Context()
# socket = context.socket(zmq.REQ)
# server_public = zmq.auth.load_certificate("public_keys/server.key")[0]
# client_public, client_secret = zmq.auth.load_certificate("private_keys/client.key_secret")
# socket.curve_secretkey = client_secret
# socket.curve_publickey = client_public
# socket.curve_serverkey = server_public
# socket.connect(f"tcp://{ip}:{port}")
# socket.send_json([name, "ReadValue()"]); socket.recv_json()

# ip = "10.10.222.13"
# port = 12346
# name = "SynthHD Pro"
# import zmq
# import zmq.auth
# context = zmq.Context()
# socket = context.socket(zmq.REQ)
# server_public = zmq.auth.load_certificate("public_keys/server.key")[0]
# client_public, client_secret = zmq.auth.load_certificate("private_keys/client.key_secret")
# socket.curve_secretkey = client_secret
# socket.curve_publickey = client_public
# socket.curve_serverkey = server_public
# socket.connect(f"tcp://{ip}:{port}")
# socket.send_json([name, "ReadValue()"]); socket.recv_json()

# ip = "localhost"
# port = 12347
# name = "CTC100"
# import zmq
# import zmq.auth
# context = zmq.Context()
# socket = context.socket(zmq.REQ)
# server_public = zmq.auth.load_certificate("public_keys/server.key")[0]
# client_public, client_secret = zmq.auth.load_certificate("private_keys/client.key_secret")
# socket.curve_secretkey = client_secret
# socket.curve_publickey = client_public
# socket.curve_serverkey = server_public
# socket.connect(f"tcp://{ip}:{port}")
# socket.send_json([name, "ReadValue()"]); socket.recv_json()
