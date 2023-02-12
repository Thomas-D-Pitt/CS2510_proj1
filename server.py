import sys, argparse, os
import rpyc as rpc
from threading import Thread
from time import sleep, time
from rpyc.utils.server import ThreadedServer

class Chatroom:
    
    def __init__(self, name):
        self.participants = []
        self.participantHeartbeats = {}
        self.messages = []
        self.name = name

        purge_thread = Thread(target=self.purge) 
        purge_thread.start()

    def purge(self):
        timeout = 10
        while True:
            sleep(timeout)
            now = time()
            for user in self.participants:
                print(user, self.participantHeartbeats[user], now)
                if self.participantHeartbeats[user] - now > timeout:
                    self.remove_chatter(user)

    def add_chatter(self, username):
        self.participants.append((username))
        self.participantHeartbeats[username] = time()
        self.participants = sorted(self.participants)
        return True

    def remove_chatter(self, username):
        self.participantHeartbeats[username] = None
        return self.participants.remove(username)

    def newMessage(self, user, message):
        self.messages.append((len(self.messages), user, message, []))

    def heartbeat(self, user):
        self.participantHeartbeats[user] = time()

    def get_messages(self, user, number):

        self.heartbeat(user)

        if number == -1:
            val = []
            for id, user, message, likes in self.messages:
                val.append((id, user, message, len(likes)))
            return val

        if len(self.messages) <= number:
            val = []
            for id, user, message, likes in self.messages:
                val.append((id, user, message, len(likes)))
            return val

        val = []
        for id, user, message, likes in self.messages[-number:]:
            val.append((id, user, message, len(likes)))
        return val

    def likeMessage(self, user, messageid):
        if user not in self.messages[messageid][3]:
            self.messages[messageid][3].append(user)
            return True
        else:
            return False

    def unlikeMessage(self, user, messageid):
        if user in self.messages[messageid][3]:
            self.messages[messageid][3].remove(user)
            return True
        else:
            return False

class Server():
    

    def __init__(self):
        self.chatrooms = []
        receive_thread = Thread(target=self.update_loop) 
        receive_thread.start()

    def getRoom(self, roomName):
        if roomName == None: return None

        for room in self.chatrooms:
            if room.name == roomName:
                return room

        return None

    def join(self, user, roomName):
        if user == None:
            return False

        room = self.getRoom(roomName)
        if room:
            return room.add_chatter(user)
            
        newRoom = Chatroom(roomName)
        self.chatrooms.append(newRoom)
        return newRoom.add_chatter(user)

    def leave(self, user, roomName):
        if user == None:
            return False

        room = self.getRoom(roomName)
        if room:
            return room.remove_chatter(user)

        return False

    def availableRooms(self):
        return [room.name for room in self.chatrooms]

    def newMessage(self, user, roomName, message):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            room.newMessage(user, message)
            return True
        else:
            return False

    def getMessages(self, user, roomName, number = 10):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            return room.get_messages(user, number)
        else:
            return None

    def getChatters(self, roomName):
        room = self.getRoom(roomName)
        if room:
            return room.participants
        else:
            return None

    def likeMessage(self, user, roomName, messageid):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            return room.likeMessage(user, messageid)
        else:
            return False

    def unlikeMessage(self, user, roomName, messageid):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            return room.unlikeMessage(user, messageid)
        else:
            return False

    def update_loop(self):
        rate = .5
        os.system('clear')
        while True:
            #os.system('clear')
            print(F"Active rooms:")
            count = 1
            for room in self.chatrooms:
                print(F"Room {count}: {room.name}, {len(room.participants)} active users")
                count += 1
            sleep(1/rate)

class Connection(rpc.Service):

    def on_connect(self, conn):
        self.clientName = None
        self.clientRoom = None

    def on_disconnect(self, conn):
        if self.clientName and self.clientRoom:
            SERVER.leave(self.clientName, self.clientRoom)

    def exposed_getMessages(self, *args, **kwargs):
        global SERVER
        return SERVER.getMessages(*args, **kwargs)

    def exposed_getChatters(self, *args, **kwargs):
        global SERVER
        return SERVER.getChatters(*args, **kwargs)

    def exposed_newMessage(self, *args, **kwargs):
        global SERVER
        return SERVER.newMessage(*args, **kwargs)

    def exposed_availableRooms(self, *args, **kwargs):
        global SERVER
        return SERVER.availableRooms(*args, **kwargs)

    def exposed_join(self, user, roomName):
        global SERVER
        success = SERVER.join(user, roomName)
        if success:
            self.clientName = user
            self.clientRoom = roomName
        return success

    def exposed_leave(self, *args, **kwargs):
        global SERVER
        success = SERVER.leave(*args, **kwargs)
        if success:
            self.clientName = None
            self.clientRoom = None
        return success

    def exposed_like(self, *args, **kwargs):
        global SERVER
        return SERVER.likeMessage(*args, **kwargs)

    def exposed_unlike(self, *args, **kwargs):
        global SERVER
        return SERVER.unlikeMessage(*args, **kwargs)

    def exposed_getServerInfo(self):
        global SERVER
        return str(SERVER)

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat server")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    return parser.parse_args()

if __name__ == '__main__':
    global SERVER
    print("Chat Server")
    args = get_args(sys.argv[1:])
    SERVER = Server()
    connectionHandler = ThreadedServer(Connection, port = args.port, listener_timeout=2)
    connectionHandler.start()