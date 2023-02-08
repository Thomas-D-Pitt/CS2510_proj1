import sys, argparse
import rpyc as rpc
from rpyc.utils.server import ForkingServer

class Chatroom:
    participants = []
    messages = []
    def __init__(self, name):
        self.name = name

    def add_chatter(self, username):
        self.participants.append(username)
        self.participants = sorted(self.participants)
        return True

    def remove_chatter(self, username):
        self.participants.remove(username)

    def newMessage(self, user, message):
        self.messages.append((user, message))

class Server(rpc.Service):
    chatrooms = []

    def getRoom(self, roomName):
        if roomName == None: return None

        for room in self.chatrooms:
            if room.name == roomName:
                return room

        return None

    def exposed_join(self, user, roomName):
        if user == None:
            return False

        room = self.getRoom(roomName)
        if room:
            return room.add_chatter(user)
            

        newRoom = Chatroom(roomName)
        self.chatrooms.append(newRoom)
        newRoom.add_chatter(user)
        return True

    def exposed_availableRooms(self):
        return [room.name for room in self.chatrooms]

    def exposed_newMessage(self, user, roomName, message):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            room.newMessage(user, message)
            return True
        else:
            return False

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat server")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    return parser.parse_args()

if __name__ == '__main__':
    print("Chat Server")
    args = get_args(sys.argv[1:])
    server = ForkingServer(Server, port = args.port)
    server.start()