import sys, argparse, os
from threading import Thread
from time import sleep
import rpyc as rpc

class Client():
    name = None
    room = None
    lastContent = None
    lastChatters = None
    displayedMessages = None
    def __init__(self, address, port):
        self.conn = rpc.connect(address, port)
        
        print("Available Rooms:", self.get_available_rooms())

        receive_thread = Thread(target=self.update_loop) 
        receive_thread.start()

        input_thread = Thread(target=self.input_loop) 
        input_thread.start()

    def set_name(self, name):
        if self.room == None:
            self.name = name
        else:
            self.conn.root.exposed_leave(self.name, self.room)
            self.name = name

    def join_room(self, room):
        if self.conn.root.exposed_join(self.name, room):
            self.room = room
            return True
        else:
            print("Error joining room")
            return False

    def get_available_rooms(self):
        return self.conn.root.exposed_availableRooms()

    def send_message(self, message):
        if self.conn.root.exposed_newMessage(self.name, self.room, message):
            return True
        else:
            print("Error sending message")
            return False

    def get_chatters(self, room):
        return self.conn.root.exposed_getChatters(room)

    def get_messages(self):
        return self.conn.root.exposed_getMessages(self.name, self.room)

    def input_loop(self):
        sleep(.1)
        while True:
            cmd = input("").split(" ", 1)
            if len(cmd) == 2:

                if cmd[0] == "a":
                    self.send_message(cmd[1])

                elif cmd[0] == "u":
                    self.set_name(cmd[1])
                    print(F"Username set to {cmd[1]}")

                elif cmd[0] == "j":
                    if self.join_room(cmd[1]):
                        print(F"joined {cmd[1]}")

                elif cmd[0] == "l":
                    if self.displayedMessages and len(self.displayedMessages) > int(cmd[1]) - 1:
                        messageid = self.displayedMessages[int(cmd[1]) - 1][0]
                        self.conn.root.exposed_like(self.name, self.room, messageid)

                elif cmd[0] == "q":
                    self.conn.root.exposed_leave(self.name, self.room)
                    self.room = None

                else:
                    print(F"Unknown command: {cmd[0]}")
            else:
                print(F"Invalid Command")

    def update_loop(self):
        rate = .2
        os.system('clear')
        print("Chat program started...")
        while True:

            newContent = self.get_messages()
            if newContent == None: newContent = []
            newChatters = self.get_chatters(self.room)
            if newContent == self.lastContent and newChatters == self.lastChatters:
                change = False

                if newContent and self.lastContent:
                    index = 0
                    for id, sender, msg, likes in newContent:
                        print(id, sender, msg, likes, self.lastContent[index])
                        if likes != self.lastContent[index][3]:
                            change = True
                            
                            break
                        index += 1

                if change == False:
                    sleep(1/rate)
                    continue
            
            os.system('clear')
            count = 1
            print(F"Group: {self.room} \nParticipants:{newChatters}")
            for id, sender, msg, likes in newContent:
                if len(likes) != 0:
                    print(F"{count}. {sender}: {msg}\t({len(likes)} Likes)")
                else:
                    print(F"{count}. {sender}: {msg}")
                count += 1
            self.lastContent = newContent[-10:]
            self.displayedMessages = newContent
            self.lastChatters = newChatters
            sleep(1/rate)
        

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat client")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    parser.add_argument('-a', '--address', required=False, default="localhost", type=str)
    return parser.parse_args()

if __name__ == '__main__':
    args = get_args(sys.argv[1:])
    client = Client(args.address, args.port)