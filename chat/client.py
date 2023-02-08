import sys, argparse
import rpyc as rpc

class Client():
    def __init__(self, address, port):
        conn = rpc.connect(address, port)
        conn.root.exposed_join("test room")
        print(conn.root.exposed_availableRooms())

        self.conn = conn

    def input_loop(self):
        pass

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat client")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    parser.add_argument('-a', '--address', required=False, default="localhost", type=str)
    return parser.parse_args()

if __name__ == '__main__':
    args = get_args(sys.argv[1:])
    client = Client(args.address, args.port)