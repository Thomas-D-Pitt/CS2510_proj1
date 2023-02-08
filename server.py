import sys, argparse
import rpyc as rpc
from rpyc.utils.server import ForkingServer

class Chatroom:
    participants = []
    def __init__(self, name):
        self.name = name

    def add_chatter(self, username):
        self.participants.append(username)
        self.participants = sorted(self.participants)

    def remove_chatter(self, username):
        self.participants.remove(username)

class Server(rpc.Service):
    chatrooms = []

    def exposed_join(self, user, roomName):
        for room in self.chatrooms:
            if room.name == roomName:
                room.add_chatter(user)
                return

        self.chatrooms.append(Chatroom(roomName))

    def exposed_availableRooms(self):
        return [room.name for room in self.chatrooms]

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat server")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    return parser.parse_args()

if __name__ == '__main__':
    print("Chat Server")
    args = get_args(sys.argv[1:])
    server = ForkingServer(Server, port = args.port)
    server.start()