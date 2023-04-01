import sys, argparse, os, json
import rpyc as rpc
from threading import Thread, Lock
from time import sleep, time
from rpyc.utils.server import ThreadedServer
import datetime

SERVER_ADDRESSES = {
    0 : "172.30.100.101:12000",
    1 : "172.30.100.102:12000",
    2 : "172.30.100.103:12000",
    3 : "172.30.100.104:12000",
    4 : "172.30.100.105:12000"
}

### Decorator functions ###
def with_lock(func):
    def inner(*args, **kwargs):
        global LOCK
        with LOCK:
            result = func(*args, **kwargs)
        return result
        
def write_function(func):
    # Handles all of the additional code that should be run for each write to the server
    def inner(self, *args, **kwargs):

        
        
        if type(self) != Server:
            raise Exception("invalid use of write_function decorator")

        receivingServer = int(kwargs.pop('receivingServer', self.index))
        fromOwnLog = kwargs.pop('fromOwnLog', False)

        
        
        self.vector_stamp[receivingServer] += 1
        if not fromOwnLog: # save command to disk
            event_stamp = self.vector_stamp[receivingServer]
            with open(F"server{self.index}_log.txt", "a") as myfile:
                cmdString = F"{receivingServer}|{event_stamp}|{func.__name__}|{args}|{json.dumps(kwargs)}\n"
                myfile.write(cmdString)

            print(F"Write function Called: {receivingServer}|{event_stamp}|{func.__name__}|{args}|{json.dumps(kwargs)}")

            if receivingServer == self.index:
                t = Thread(target = self.serverShareCmd, args = [cmdString], daemon=True)
                t.start()
                #self.serverShareCmd(cmdString)

        return func(self, *args, **kwargs)

    return inner


class Chatroom:
    
    def __init__(self, name):
        self.participants = []
        self.participantHeartbeats = {}
        self.messages = []
        self.name = name

        purge_thread = Thread(target=self.purge) 
        purge_thread.start()

    def purge(self):
        # Removes inactive users from chatroom as determined by last heartbeat
        timeout = 10
        while True:
            sleep(timeout)
            now = time()
            for user in self.participants:
                if self.participantHeartbeats[user] and self.participantHeartbeats[user] - now > timeout:
                    self.remove_chatter(user)

    def add_chatter(self, username):
        self.participants.append((username))
        self.participantHeartbeats[username] = time()
        self.participants = sorted(self.participants)
        return True

    def remove_chatter(self, username):
        self.participantHeartbeats[username] = None
        if username in self.participants:
            return self.participants.remove(username)
        return False

    def newMessage(self, user, message, timestamp):
        timestamp = datetime.datetime.strptime(str(timestamp), '%Y-%m-%d %H:%M:%S.%f')

        data = (len(self.messages), user, message, [], timestamp)
        done = False
        for i in range(len(self.messages)):
            if self.messages[i][4] > timestamp:
                self.messages.insert(i, data)
                done = True
                break

        if done == False:
            self.messages.append(data)

    def heartbeat(self, user):
        # used for keeping track of last time a user polled chatroom 
        self.participantHeartbeats[user] = time()

    def get_messages(self, user, number):

        self.heartbeat(user)

        if number == -1: # return all messages
            val = []
            for id, user, message, likes, _ in self.messages:
                likeCount = self.sumLikes(likes)
                val.append((id, user, message, likeCount))
            return val

        if len(self.messages) <= number: #asking for more messages than exist, return all existing messages
            val = []
            for id, user, message, likes, _ in self.messages:
                likeCount = self.sumLikes(likes)
                val.append((id, user, message, likeCount))
            return val

        val = [] # return (number) most recent messages
        for id, user, message, likes, _ in self.messages[-number:]:
            likeCount = self.sumLikes(likes)
            val.append((id, user, message, likeCount))
        return val

    def likeMessage(self, user, messageid, timestamp, value = True):
        for i in range(len(self.messages[messageid][3])):
            cUser, cTimestamp, cVal = self.messages[messageid][3][i]

            if user == cUser:
                if cVal == value: # overwritting existing like with newer timestamp
                    self.messages[messageid][3][i] = (user, timestamp, value)
                    return False

                elif cVal != value: # prior removed like
                    if cTimestamp < timestamp: # new like is more recent than removal
                        self.messages[messageid][3][i] = (user, timestamp, value)
                        return True
                    else:
                        return False

        self.messages[messageid][3].append((user, timestamp, value))
        return True

    def unlikeMessage(self, user, messageid, timestamp):
        # exact same as likeMessage code, just store a different value
        self.likeMessage(user, messageid, timestamp, value = False)

    def sumLikes(self, likes):
        sum = 0
        for _, _, value in likes:
            if value == True:
                sum += 1
        return sum

class Server():
    """
    manages all chatroooms, and forwarding RPCs to chatrooms when appropriate
    """

    def __init__(self, index):
        self.index = index
        self.clear_terminal = False
        self.display_status = False
        self.chatrooms = []
        self.messagesToProcess = {}
        self.vector_stamp = [0 for _ in range(len(SERVER_ADDRESSES.keys()))]

        for key in SERVER_ADDRESSES.keys():
            self.messagesToProcess[key] = []

        if os.path.isfile(F"server{self.index}_log.txt"):
            self.recoverFromCrash()

        receive_thread = Thread(target=self.update_loop, daemon=True) 
        receive_thread.start()

        entropy_thread = Thread(target=self.anti_entropy, daemon=True) 
        entropy_thread.start()
        

    @write_function
    def example_write_func(self, a, b, c):
        return "sneep snoop"

    def recoverFromCrash(self):
        # rerun all commands in log file
        if os.path.isfile(F"server{self.index}_log.txt"):
            with open(F"server{self.index}_log.txt", "r") as myfile:
                msgs = myfile.readlines()

            for msg in msgs:
                self.processCmdString(msg, fromOwnLog=True)

            print("Recovered from crash, vector_stamp:", self.vector_stamp)

    def serverDataGet(self, otherServerIndex):
        # get all unknown information from another server
        if otherServerIndex != self.index:
            address, port = SERVER_ADDRESSES[otherServerIndex].split(":", 1)
            conn = rpc.connect(address, port)

            newMessages = conn.root.exposed_getServerData(self.vector_stamp)
            
            for message in newMessages:
                self.processCmdString(message)
            conn.close()
            

    def serverDataGive(self, otherVector):
        # give all info to server that occurred after otherVector
        filtered_msgs = []
        if os.path.isfile(F"server{self.index}_log.txt"):
            with open(F"server{self.index}_log.txt", "r") as myfile:
                msgs = myfile.readlines()
            
            for msg in msgs:
                receivingServer, event_stamp, func, args, kwargs = msg.replace("\n", "").split("|")
                if otherVector[int(receivingServer)] < int(event_stamp):
                    filtered_msgs.append(msg)
        return filtered_msgs

    def serverShareCmd(self, cmd):
        for key, value in SERVER_ADDRESSES.items():
            t = Thread(target = self._serverShareCmdHelper, args = [key, value, cmd])
            t.start()

    def _serverShareCmdHelper(self, key, value, cmd):
        try:
            if key == self.index: return

            address, port = value.split(":", 1)
            conn = rpc.connect(address, port)
            conn.root.exposed_processCmdString(cmd)
            conn.close()
        except Exception as e:
            print(F"Error in serverShareCmd on {key}: {e}")

            
    def processCmdString(self, cmd, fromOwnLog = False):
        # run an RPC that was stored to a string
        receivingServer, event_stamp, func, args, kwargs = cmd.replace("\n", "").split("|")

        #only run if it is the next command for a given server, otherwise save it for later
        if int(event_stamp) == self.vector_stamp[int(receivingServer)] + 1:
            args = eval(args)
            kwargs = json.loads(kwargs)

            func = getattr(self, func)
            func(*args, **kwargs, receivingServer = receivingServer, fromOwnLog = fromOwnLog)

            for message in self.messagesToProcess[int(receivingServer)]:
                # try and run other commands waiting to be processed
                self.messagesToProcess[int(receivingServer)].remove(message)
                if not self.processCmdString(message):
                    self.messagesToProcess[int(receivingServer)].append(message)

            return True

        else:
            self.messagesToProcess[int(receivingServer)].append(cmd)
            return False

    def anti_entropy(self):
        # get and process data from other servers
        #return
        sleep(1)
        while True:
            for key in SERVER_ADDRESSES.keys():
                try:
                    self.serverDataGet(key)
                except Exception as e:
                    print(F"Error in anti-entropy on {key}: {e}")

            sleep(1)

    def getRoom(self, roomName):
        if roomName == None: return None

        for room in self.chatrooms:
            if room.name == roomName:
                return room

        return None

    @write_function
    def join(self, user, roomName, timeStamp):
        # adds user to chatroom, or creates chatroom if it does not exist 
        if user == None:
            return False

        room = self.getRoom(roomName)
        if room:
            return room.add_chatter(user)
            
        newRoom = Chatroom(roomName)
        self.chatrooms.append(newRoom)
        return newRoom.add_chatter(user)

    @write_function
    def leave(self, user, roomName, timeStamp):
        if user == None:
            return False

        room = self.getRoom(roomName)
        if room :
                return room.remove_chatter(user)

        return False

    def availableRooms(self):
        return [room.name for room in self.chatrooms]

    @write_function
    def newMessage(self, user, roomName, message, timeStamp):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            room.newMessage(user, message, timeStamp)
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

    @write_function
    def likeMessage(self, user, roomName, messageid, timeStamp):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            return room.likeMessage(user, messageid, timeStamp)
        else:
            return False

    @write_function
    def unlikeMessage(self, user, roomName, messageid, timeStamp):
        room = self.getRoom(roomName)
        if room and user in room.participants:
            return room.unlikeMessage(user, messageid, timeStamp)
        else:
            return False

    def update_loop(self):
        # prints out current status of server and available chatrooms

        rate = .5
        if self.clear_terminal:
            os.system('clear')
        while True:
            if self.clear_terminal:
                os.system('clear')
            if self.display_status:
                print(F"Active rooms:")
                count = 1
                for room in self.chatrooms:
                    print(F"Room {count}: {room.name}, {len(room.participants)} active users")
                    count += 1
            sleep(1/rate)

class Connection(rpc.Service):
    """
    Manages forwarding RPCs to server object shared across all connections
    """
    def on_connect(self, conn):
        self.clientName = None
        self.clientRoom = None

    def on_disconnect(self, conn):
        if self.clientName and self.clientRoom:
            try:
                SERVER.leave(self.clientName, self.clientRoom, datetime.now())
            except:
                print(F'attempted to remove {self.clientName} from {self.clientRoom} but failed')

    def exposed_getMessages(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            val = SERVER.getMessages(*args, **kwargs)
        return val


    def exposed_getChatters(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            val = SERVER.getChatters(*args, **kwargs)
        return val



    def exposed_newMessage(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            val = SERVER.newMessage(*args, **kwargs)
        return val



    def exposed_availableRooms(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            val = SERVER.availableRooms(*args, **kwargs)
        return val



    def exposed_join(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            success = SERVER.join(*args, **kwargs) 
        if success:
            self.clientName = args[0]
            self.clientRoom = args[1]
        return success


    def exposed_leave(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            success = SERVER.leave(*args, **kwargs)

        if success:
            self.clientName = None
            self.clientRoom = None
        return success


    def exposed_like(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            val = SERVER.likeMessage(*args, **kwargs)
        return val



    def exposed_unlike(self, *args, **kwargs):
        global SERVER, LOCK
        with LOCK:
            val = SERVER.unlikeMessage(*args, **kwargs)
        return val


    def exposed_getServerInfo(self):
        global SERVER, LOCK
        with LOCK:
            val = str(SERVER)
        return val


    def exposed_getServerData(self, *args, **kwargs):
        global SERVER
        with LOCK:
            val = SERVER.serverDataGive(*args, **kwargs)
        return val

    def exposed_processCmdString(self, *args, **kwargs):
        global SERVER
        with LOCK:
            val = SERVER.processCmdString(*args, **kwargs)
        return val

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat server")
    parser.add_argument('-id', '--id', required=False, default=1, type=int)
    p = parser.parse_args()
    p.id -= 1
    p.address = SERVER_ADDRESSES[p.id].split(":", 1)[0]
    p.port = SERVER_ADDRESSES[p.id].split(":", 1)[1]
    return p

if __name__ == '__main__':
    global SERVER, LOCK
    LOCK = Lock()
    print("Chat Server")
    args = get_args(sys.argv[1:])
    SERVER = Server(args.id)

    connectionHandler = ThreadedServer(Connection, port = args.port, listener_timeout=2)
    connectionHandler.start()