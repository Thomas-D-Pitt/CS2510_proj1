import sys, argparse, os
from datetime import datetime
from threading import Thread
from time import sleep
import rpyc as rpc

SERVER_ADDRESSES = {
    0 : "172.30.100.101:12000",
    1 : "172.30.100.102:12000",
    2 : "172.30.100.103:12000",
    3 : "172.30.100.104:12000",
    4 : "172.30.100.105:12000"
}

class Client():
    
    def __init__(self):
        self.name = None
        self.room = None
        self.lastContent = None
        self.lastChatters = None
        self.displayedMessages = None
        self.fetchAll = False
        self.conn = None

        self.receive_thread = Thread(target=self.update_loop, daemon=True) # infinite loop to update screen
        self.receive_thread.start()

        self.input_thread = Thread(target=self.input_loop) # infinite loop to receive user input
        self.input_thread.start()

    def connect(self, arg):
        if self.conn:
            if self.conn:
                self.conn.root.exposed_leave(self.name, self.room)
                self.room = None

        if ":" in arg:
            address, port = arg.split(":", 1)
        else:
            address, port = SERVER_ADDRESSES[int(arg) - 1].split(":", 1)

        self.conn = rpc.connect(address, port)
        print("Available Rooms:", self.get_available_rooms())

    def set_name(self, name):
        if self.room == None:
            self.name = name
        else:
            self.conn.root.exposed_leave(self.name, self.room, datetime.now())
            self.name = name

    def join_room(self, room):
        if self.conn.root.exposed_join(self.name, room, datetime.now()):
            self.room = room
            return True
        else:
            print("Error joining room")
            return False

    def get_available_rooms(self):
        return self.conn.root.exposed_availableRooms()

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

    def input_loop(self):
        sleep(.1)
        while True:
            try:
                raw = input("")
                cmd = raw.split(" ", 1)
                if len(cmd) == 2: # commands with arguments

                    if cmd[0] == "a": #append message
                        self.send_message(cmd[1])

                    elif cmd[0] == "u": #set username
                        if self.room and self.name and self.conn:
                            self.conn.root.exposed_leave(self.name, self.room)
                            self.room = None

                        self.set_name(cmd[1])
                        print(F"Username set to {cmd[1]}")

                    elif cmd[0] == "j": #join chatroom
                        if self.room and self.name and self.conn:
                            self.conn.root.exposed_leave(self.name, self.room)
                            self.room = None

                        if self.join_room(cmd[1]):
                            print(F"joined {cmd[1]}")

                    elif cmd[0] == "l": #like message
                        if  self.conn and self.displayedMessages and len(self.displayedMessages) > int(cmd[1]) - 1:
                            messageid = self.displayedMessages[int(cmd[1]) - 1][0]
                            self.conn.root.exposed_like(self.name, self.room, messageid, datetime.now())

                    elif cmd[0] == "r": #remove message like
                        if self.conn and self.displayedMessages and len(self.displayedMessages) > int(cmd[1]) - 1:
                            messageid = self.displayedMessages[int(cmd[1]) - 1][0]
                            self.conn.root.exposed_unlike(self.name, self.room, messageid, datetime.now())

                    elif cmd[0] == "c": # connect to server
                        self.connect(cmd[1])

                    else:
                        print(F"Unknown command: {cmd[0]}")
                else: # commands with no arguments
                    if cmd[0] == "p": #print past messages
                        self.fetchAll = True
                        self.lastContent = None
                    elif cmd[0] == "q": #quit
                        if self.conn:
                            self.conn.root.exposed_leave(self.name, self.room)
                        self.room = None
                        os.system('clear')
                        sys.exit()
                    else:
                        print(F"Invalid Command")
            except Exception as e:
                print(F'Exception "{e}" raised while processing "{raw}"')

    def update_loop(self):
        rate = 3
        os.system('clear')
        print("Chat program started...")
        while True:
            if not self.conn:
                sleep(1/rate)
                continue

            newContent = self.get_messages()

            if newContent == None: newContent = []

            newChatters = self.get_chatters(self.room)

            if newContent == self.lastContent and str(newChatters) == str(self.lastChatters):
                # if nothing has changed server-side do nothing
                sleep(0.5/rate)
                continue
            
            # if there are changes...
            os.system('clear')
            count = 1
            print(F"Group: {self.room} \nParticipants:{newChatters}")
            for id, sender, msg, likes in newContent:
                if likes != 0:
                    print(F"{count}. {sender}: {msg}\t({likes} Likes)")
                else:
                    print(F"{count}. {sender}: {msg}")
                count += 1

            sleep(1/rate)
            self.lastContent = newContent[-10:]
            self.displayedMessages = newContent
            self.lastChatters = str(newChatters)
            
        

def get_args(argv):

    parser = argparse.ArgumentParser(description="chat client")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    parser.add_argument('-a', '--address', required=False, default="localhost", type=str)
    return parser.parse_args()

if __name__ == '__main__':
    #args = get_args(sys.argv[1:])

    print("connect to server using 'c <address>:<port>'")
    print("suggested: c localhost:12000")
    address = None
    port = None

    # start client after connecting to server
    client = Client()