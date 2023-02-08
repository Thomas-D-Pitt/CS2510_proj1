import sys, argparse
import rpyc as rpc
from threading import Thread
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

    def get_messages(self, number):
        if number == -1:
            return self.messages

        if len(self.messages) <= number:
            return self.messages

        return self.messages[-number:]

class Server():
    chatrooms = []

    def __init__(self):
        receive_thread = Thread(target=self.update_loop) 
        receive_thread.start()

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

    def exposed_getMessages(self, user, roomName, number = 10):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            return room.get_messages(number)
        else:
            return None


    def update_loop(self):
        rate = .5
        os.system('clear')
        while True:
            os.system('clear')
            print(F"Active rooms:")
            count = 1
            for room in self.chatrooms:
                print(F"Room {count}: {room.name}, {len(room.participants)} active users")
                count += 1
            self.lastContent = newContent[-10:]
            sleep(1/rate)

class Connection(rpc.Service):
    def __getattribute__(name):
        print("do threading")
        SERVER.__getattribute__(name)

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat server")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    return parser.parse_args()

if __name__ == '__main__':
    print("Chat Server")
    args = get_args(sys.argv[1:])
    SERVER = Server()
    connectionHandler = ForkingServer(Connection, port = args.port)
    connectionHandler.start()