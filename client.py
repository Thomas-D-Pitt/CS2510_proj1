import sys, argparse, os
from datetime import datetime
from threading import Thread, Lock
from time import sleep
import rpyc as rpc

SERVER_ADDRESSES = {
    0 : "172.30.100.101:12000",
    1 : "172.30.100.102:12000",
    2 : "172.30.100.103:12000",
    3 : "172.30.100.104:12000",
    4 : "172.30.100.105:12000"
}

def with_lock(func):
    def inner(*args, **kwargs):
        global LOCK
        with LOCK:
            result = func(*args, **kwargs)
        return result
    
    return inner

class Client():
    
    def __init__(self, restart = False):
        self.name = None
        self.room = None
        self.lastContent = None
        self.lastChatters = None
        self.displayedMessages = None
        self.fetchAll = False
        self.conn = None
        self.serverid = None
        self.terminateLock = Lock()
        self.terminated = False

        self.receive_thread = Thread(target=self.update_loop, daemon=True, args=[restart]) # infinite loop to update screen
        self.receive_thread.start()


    @with_lock
    def connect(self, arg):
        if len(arg) == 0 or arg == None:
            print("cannot connect to 'None'")
            return False
        
        self.disconnect()
    
        if ":" in arg:
            address, port = arg.split(":", 1)
        else:
            address, port = SERVER_ADDRESSES[int(arg) - 1].split(":", 1)

        self.conn = rpc.connect(address, port)
        self.serverid = str(arg)
        os.system('clear')
        print(F"connecting to {self.serverid}")
    
        try:
            _ = self.get_available_rooms()
            os.system('clear')
            print(F"SERVER: {self.serverid}")
        except Exception as e:
            print(F"error connecting: {e}")

    
    def disconnect(self):
        if self.conn:
            self.conn.root.exposed_leave(self.name, self.room, datetime.now())
            self.conn = None
        self.room = None
        #os.system('clear')
        
    def set_name(self, name):
        if len(name) < 1:
            print("invalid name")
            return

        self.leave()
        os.system('clear')
        print(F"SERVER: {self.serverid}")
        self.name = name

    @with_lock
    def join_room(self, room):
        if self.name == None:
            print("You must select a name first")
            return False
        
        if self.conn and self.conn.root.exposed_join(self.name, room, datetime.now()):
            self.room = room
            return True
        else:
            print("Error joining room")
            return False

    def get_available_rooms(self):
        return self.conn.root.exposed_availableRooms()

    @with_lock
    def send_message(self, message):
        if self.conn.root.exposed_newMessage(self.name, self.room, message, datetime.now()):
            return True
        else:
            print("Error sending message")
            return False


    def get_chatters(self, room):
        return self.conn.root.exposed_getChatters(room)

    def get_messages(self):
        if self.fetchAll:
            self.fetchAll = False
            return self.conn.root.exposed_getMessages(self.name, self.room, -1)
        return self.conn.root.exposed_getMessages(self.name, self.room)
    
    @with_lock
    def leave(self):
        if self.room and self.name and self.conn:
            self.conn.root.exposed_leave(self.name, self.room, datetime.now())
            self.room = None

    @with_lock
    def like(self, index):
        if  self.conn and self.displayedMessages and len(self.displayedMessages) > int(index) - 1:
            messageid = self.displayedMessages[int(index) - 1][0]
            self.conn.root.exposed_like(self.name, self.room, messageid, datetime.now())

    @with_lock
    def unlike(self, index):
        if self.conn and self.displayedMessages and len(self.displayedMessages) > int(index) - 1:
            messageid = self.displayedMessages[int(index) - 1][0]
            self.conn.root.exposed_unlike(self.name, self.room, messageid, datetime.now())

    @with_lock
    def reachableServers(self):
        result = self.conn.root.exposed_reachableServers()
        for i in range(len(result)):
            print(F"server {i+1} reachable: {result[i]}")

    def input_loop(self):
        sleep(.1)
        while True:
            with self.terminateLock:
                if self.terminated:
                    raise EOFError
            try:
                raw = input("")
                cmd = raw.split(" ", 1)
                if len(cmd) == 2: # commands with arguments

                    if cmd[0] == "a": #append message
                        self.send_message(cmd[1])

                    elif cmd[0] == "u": #set username
                        self.leave()

                        self.set_name(cmd[1])
                        print(F"Username set to {cmd[1]}")

                    elif cmd[0] == "j": #join chatroom
                        self.leave()

                        if self.join_room(cmd[1]):
                            print(F"joined {cmd[1]}")

                    elif cmd[0] == "l": #like message
                        self.like(cmd[1])

                    elif cmd[0] == "r": #remove message like
                        self.unlike(cmd[1])

                    elif cmd[0] == "c": # connect to server
                        try:
                            self.connect(cmd[1])
                        except OSError as e:
                            print(F"Error while connecting to server: {e}")

                    else:
                        print(F"Unknown command: {cmd[0]}")
                else: # commands with no arguments
                    if cmd[0] == "p": #print past messages
                        self.fetchAll = True
                        self.lastContent = None
                    elif cmd[0] == "v": #quit
                        self.reachableServers()
                    elif cmd[0] == "q": #quit
                        self.disconnect()
                        sys.exit()
                    else:
                        print(F"Invalid Command")
            except FileNotFoundError as e:
                print(F'Exception "{e}" raised while processing "{raw}"')

    def update_loop(self, restart = False):
        global LOCK
        rate = 3
        os.system('clear')
        if restart:
            print("client disconnected, please reconnect and reselect name")
        else:    
            print("Chat program started...")
        print("connect to server using 'c <address>:<port>'")
        print("suggested: c <1-5>")
        try:
            while True:
                sleepTime = 1
                if not self.conn or not self.room:
                    sleep(sleepTime/rate)
                    continue
                
                with LOCK:

                    newContent = self.get_messages()

                    if newContent == None: newContent = []

                    newChatters = self.get_chatters(self.room)


                    if newContent == self.lastContent and str(newChatters) == str(self.lastChatters):
                        sleepTime = 0.5
                    
                    else:
                        # if there are changes...
                        os.system('clear')
                        count = 1
                        print(F"SERVER: {self.serverid}")
                        print(F"Group: {self.room} \nParticipants:{newChatters}")
                        for id, sender, msg, likes in newContent:
                            if likes != 0:
                                print(F"{count}. {sender}: {msg}\t({likes} Likes)")
                            else:
                                print(F"{count}. {sender}: {msg}")
                            count += 1

                        self.lastContent = newContent[-10:]
                        self.displayedMessages = newContent
                        self.lastChatters = str(newChatters)

                sleep(sleepTime/rate)
        except EOFError:
            print("Error connecting to server pleace connect to another server")
            with self.terminateLock:
                self.terminated = True
            
            
        

def get_args(argv):

    parser = argparse.ArgumentParser(description="chat client")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    parser.add_argument('-a', '--address', required=False, default="localhost", type=str)
    return parser.parse_args()

if __name__ == '__main__':
    #args = get_args(sys.argv[1:])
    global LOCK
    LOCK = Lock()
    
    address = None
    port = None

    # start client after connecting to server
    restart = False
    while True:
        try:
            client = Client(restart)
            client.input_loop()
        except EOFError as e:
            restart = True
            print(F"client disconnected with error {e}, please reconnect")

        
