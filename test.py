import zmq
import zmq.auth
from zmq.auth.thread import ThreadAuthenticator

from pathlib import Path

def Decode(topicfilter, message):
    """
    Function decodes the message received from the publisher into a
    topic and python object via json serialization
    """
    dat = message[len(topicfilter):]
    retval = json.loads(dat)
    return retval

if __name__ == "__main__":
    ctx = zmq.Context.instance()

    file_path = Path(__file__).resolve()
    public_keys_dir = file_path.parent / "authentication" / "public_keys"
    secret_keys_dir = file_path.parent / "authentication" / "private_keys"
    # file_path = Path().cwd()
    # public_keys_dir = file_path / "authentication" / "public_keys"
    # secret_keys_dir = file_path / "authentication" / "private_keys"

    server_public_file = public_keys_dir / "server.key"
    server_public, _ = zmq.auth.load_certificate(str(server_public_file))

    client_secret_file = secret_keys_dir / "client.key_secret"
    client_public, client_secret = zmq.auth.load_certificate(str(client_secret_file))

    client = ctx.socket(zmq.REQ)

    client.curve_secretkey = client_secret
    client.curve_publickey = client_public
    client.curve_serverkey = server_public

    client.connect("tcp://127.0.0.1:12347")

    client.send_json(["SDG1032X", "ReadValue()"])

    if client.poll(1000):
        msg = client.recv_json()
        print(msg)
    else:
        print('Error')
