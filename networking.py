import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import List

import zmq
import zmq.auth
import zmq.devices
from zmq.auth.thread import ThreadAuthenticator

from protocols import CentrexGUIProtocol


class NetworkingDeviceWorker(threading.Thread):
    def __init__(self, parent: CentrexGUIProtocol, backend_port: int):
        super(NetworkingDeviceWorker, self).__init__()
        self.active = threading.Event()
        self.daemon = True
        self.parent = parent
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        # connect to the ipc backend
        # ipc doesn't work on windows, switch to tcp, port is centrex typed into
        # a keypad
        # self.socket.connect("ipc://backend.ipc")
        self.socket.connect(f"tcp://localhost:{backend_port}")

        # each worker has an unique id for the return value queue
        self.uid = uuid.uuid1().int >> 64

        logging.info(f"NetworkingDeviceWorker: initialized worker {self.uid}")

    def run(self):
        logging.info(f"NetworkingDeviceWorker: started worker {self.uid}")
        while self.active.is_set():
            # receive the request from a client
            device, command = self.socket.recv_json()
            logging.info(f"{self.uid} : {device} {command}")

            # strip both to prevent whitespace errors during eval on device
            device.strip()
            command.strip()
            # check if device present
            if device not in self.parent.devices:
                self.socket.send_json(["ERROR", "device not present"])
                continue
            dev = self.parent.devices[device]
            # check if device control is started
            if not dev.control_started:
                self.socket.send_json(["ERROR", "device not started"])
                continue
            # check if device is enabled
            elif not dev.config["control_params"]["enabled"]["value"] == 2:
                self.socket.send_json(["ERROR", "device not enabled"])
                continue
            # check if device is slow data
            # ndarrays are not serializable by default, and fast devices return
            # ndarrays on ReadValue()
            elif not dev.config["slow_data"] and command == "ReadValue()":
                self.socket.send_json(["ERROR", "device does not support slow data"])
            else:
                # put command into the networking queue
                dev.networking_commands.append((self.uid, command))
                while True:
                    # check if uid is present in return val dictionary and pop
                    # if present
                    if self.uid in dev.networking_events_queue:
                        ret_val = dev.networking_events_queue.pop(self.uid)
                        # serialize with json and send back to client
                        self.socket.send_json(["OK", ret_val])
                        break
            # need a sleep to release to other threads
            time.sleep(1e-4)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.close()
        self.context.term()


class NetworkingBroker(threading.Thread):
    def __init__(self, outward_port: int, allowed: List[str]):
        super(NetworkingBroker, self).__init__()

        self.daemon = True

        # setup authentication
        self.auth = ThreadAuthenticator()
        self.auth.start()
        self.auth.allow(*allowed)

        # load authentication keys
        file_path = Path(__file__).resolve()
        # public_keys_dir = file_path.parent / "authentication" / "public_keys"
        # self.auth.configure_curve(domain = '*', location = str(public_keys_dir))
        self.auth.configure_curve(domain="*", location=zmq.auth.base.CURVE_ALLOW_ANY)
        server_secret_file = (
            file_path.parent / "authentication" / "private_keys" / "server.key_secret"
        )
        server_public, server_secret = zmq.auth.load_certificate(
            str(server_secret_file)
        )

        # message broker for control

        device = zmq.devices.Device(zmq.QUEUE, zmq.XREP, zmq.XREQ)
        device.bind_in(f"tcp://*:{outward_port}")
        self.backend_port = device.bind_out_to_random_port("tcp://127.0.0.1")

        device.setsockopt_in(zmq.SocketOption.CURVE_SECRETKEY, server_secret)
        device.setsockopt_in(zmq.SocketOption.CURVE_PUBLICKEY, server_public)
        device.setsockopt_in(zmq.SocketOption.CURVE_SERVER, True)
        device.daemon = True

        self.device = device

        logging.info("NetworkingBroker: initialized broker")

    def __exit__(self, *args):
        for socket in self.device._sockets:
            socket.setsockopt(zmq.LINGER, 0)
            socket.close()
        try:
            self.device.context_factory().destroy()
        except OSError as e:
            if (
                "An operation was attepted on something that is not a socket"
                in e.args[0]
            ):
                logging.error(f"{e.args[0]}")
                logging.warning(e)
        return

    def run(self):
        # try-except because zmq.device throws an error when the sockets and
        # context are closed when running
        # TODO: better method of closing the message broker
        logging.info("NetworkingBroker: started broker")
        try:
            self.device.start()
        except Exception as e:
            logging.warning(e)
            pass


class Networking(threading.Thread):
    def __init__(self, parent: CentrexGUIProtocol):
        super(Networking, self).__init__()
        self.parent = parent
        self.active = threading.Event()
        self.conf = self.parent.config["networking"]

        # deamon = True ensures this thread terminates when the main threads
        # are terminated
        self.daemon = True

        self.context_readout = zmq.Context()
        self.socket_readout = self.context_readout.socket(zmq.PUB)
        self.socket_readout.bind(f"tcp://*:{self.conf['port_readout']}")

        # dictionary with timestamps of last ReadValue update per device
        self.devices_last_updated = {
            dev_name: 0 for dev_name in self.parent.devices.keys()
        }

        # initialize the broker for network control of devices
        allowed = self.conf["allowed"].split(",")
        self.control_broker = NetworkingBroker(self.conf["port_control"], allowed)

        # initialize the workers used for network control of devices
        backend_port = self.control_broker.backend_port
        backend_port = 81512
        self.workers = [
            NetworkingDeviceWorker(parent, backend_port)
            for _ in range(int(self.conf["workers"]))
        ]

    def encode(self, topic, message):
        """
        Function encodes the message from the publisher via json serialization
        """
        return topic + " " + json.dumps(message)

    def run(self):
        logging.info("Networking: started main thread")
        # start the message broker
        self.control_broker.start()
        # start the workers
        for worker in self.workers:
            worker.active.set()
            worker.start()

        for dev_name, dev in self.parent.devices.items():
            # check device running
            if not dev.control_started:
                continue
            # check device enabled
            if not dev.config["control_params"]["enabled"]["value"] == 2:
                continue

            # check if device is a network client, don't retransmit data
            # from a network client device
            if getattr(dev, "is_networking_client", None):
                continue
            logging.info(f"{dev_name} networking")

        while self.active.is_set():
            for dev_name, dev in self.parent.devices.items():
                # check device running
                if not dev.control_started:
                    continue
                # check device enabled
                if not dev.config["control_params"]["enabled"]["value"] == 2:
                    continue

                # check if device is a network client, don't retransmit data
                # from a network client device
                if getattr(dev, "is_networking_client", None):
                    continue

                if len(dev.config["plots_queue"]) > 0:
                    data = dev.config["plots_queue"][-1]
                else:
                    data = None

                if isinstance(data, list):
                    if dev.config["slow_data"]:
                        t_readout = data[0]
                        if self.devices_last_updated[dev_name] != t_readout:
                            self.devices_last_updated[dev_name] = t_readout
                            topic = f"{self.conf['name']}-{dev_name}"
                            message = [dev.time_offset + data[0]] + data[1:]
                            self.socket_readout.send_string(self.encode(topic, message))

                time.sleep(1e-5)

        # close the message broker and workers when stopping network control
        self.control_broker.__exit__()
        # logging.info("stopped control_broker")
        for worker in self.workers:
            worker.active.clear()
        logging.info("stopped workers")
        self.socket_readout.setsockopt(zmq.LINGER, 0)
        self.socket_readout.close()
        logging.info("stopped socket_readout")
        self.context_readout.term()
        logging.info("stopped contex_readout")
