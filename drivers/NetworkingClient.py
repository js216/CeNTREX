import zmq
import json
import time
import logging
import numpy as np

def wrapperNetworkClientMethods(func):
    """
    Function wrapper for all methods not rewritten in NetworkingClientClass and 
    excluding static methods
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        func.__name__+'(*{0}, **{1})'.format(args[1:], kwargs)
        retval = self.ExecuteNetworkCommand(func.__name__+'(*{0}, **{1})'.format(args[1:], kwargs))
        return retval
    return wrapper

def NetworkingClassDecorator(cls):
    """
    Decorator for the NetworkingClientClass to modify driver function for use
    with the socket client.
    """
    # don't wrap methods with this name
    ignore = ['__init__', '__enter__', '__exit__', 'OpenConnection', 
            'CloseConnection', 'ExecuteNetworkCommand', 'ReadValue', 
            'GetWarnings']
    for attr_name in dir(cls):
        attr_value = getattr(cls, attr_name)
        if isinstance(attr_value, FunctionType):
            if attr_name in ignore:
                continue
            elif not inspect.signature(attr_value).parameters.get('self'):
                # don't wrap static methods, very clunky method but couldn't
                # figure out a better way
                continue
            else:
                attribute = wrapperNetworkClientMethods(attr_value)
                setattr(cls, attr_name, attribute)
    return cls

def NetworkingClient(time_offset, connection, device, *args):
    driver = args[2]
    driver_spec = importlib.util.spec_from_file_location(
        driver,
        "drivers/" + driver + ".py",
    )

    driver_module = importlib.util.module_from_spec(driver_spec)
    driver_spec.loader.exec_module(driver_module)
    driver = getattr(driver_module, driver)

    @NetworkingClassDecorator
    class NetworkingClientClass(driver):
        def __init__(self, time_offset, device, connection, *args):
            self.time_offset = time_offset
            self.device = device
            
            self.server = connection['server']
            self.port_readout = connection['port_readout']
            self.port_control = connection['port_control']
            self.publisher = connection['publisher_name']
            self.device_name = connection['device_name']
            
            # set the control connection timeout
            self.timeout = 10e3
            # open connections to the server
            self.OpenConnection()

            self.warnings = []

            self.args = [eval(_) for _ in args]
        
        def GetWarnings():
            return self.warnings

        def OpenConnection(self):
            # starting the context
            self.context = zmq.Context()
            # opening the sockets
            self.socket_control = self.context.socket(zmq.REQ)
            self.socket_readout = self.context.socket(zmq.PUB)

            # starting readout
            topicfilter = f"{self.publisher}-{self.device_name}"
            self.socket_readout.setsockopt_string(zmq.SUBSCRIBE, topicfilter)
            # only keep the last value from the publisher in the queue
            self.socket_readout.socket.setsockopt(zmq.CONFLATE, 1)
            self.socket_readout.connect(f"tcp://{self.server}:{self.port_readout}")

            # starting control
            self.socket_control.connect(f"tcp://{self.server}:{self.port_control}")
        
        def CloseConnection(self):
            # close all connections
            self.socket_control.close()
            self.socket_readout.close()
            self.context.term()
        
        @staticmethod
        def decode(message):
            """
            Function decodes the message received from the publisher into a 
            topic and python object via json serialization
            """
            json0 = message.find('{')
            topic = message[0:json0].strip()
            retval = json.loads(message[json0:])
            return topic, retval

        def ExecuteNetworkCommand(self, command): 
            # send command to the server hosting the device
            self.socket_control.send_json([self.device, command])

            # need the timeout because REP-REQ will wait indefinitely for a 
            # reply, need to handle when a server stops or a message isn't
            # received for some other reason
            if (self.socket_control.poll(self.timeout) & zmq.POLLIN) != 0:
                status, retval = self.socket_control.recv_json()
                if status == "OK":
                    return retval
                else:
                    logging.warning(f"{device} networking warning in " +
                    +f"ExecuteNetworkCommand : error for {command} -> {retval}")
                    return np.nan

            # error handling if no reply received withing timeout
            logging.warning(f"{device} networking warning in " +
                        +"ExecuteNetworkCommand : no response from server")
            self.socket_control.setsockopt(zmq.LINGER, 0)
            self.socket_control.close()
            self.socket_control = self.context.socket(zmq.REQ)
            self.socket_control.connect(f"tcp://{self.server}:{self.port_control}")
            return np.nan

        def ReadValue(self):
            topic, retval = self.decode(self.recv_string())
            retval[0] -= time.time() - self.time_offset
            return retval




    
    return NetworkingClientClass(time_offset, connection, *args)