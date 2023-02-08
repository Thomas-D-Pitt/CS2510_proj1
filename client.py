import sys, argparse, os
from threading import Thread
from time import sleep
import rpyc as rpc

class Client():
    name = None
    room = None
    lastContent = None
    def __init__(self, address, port):
        self.conn = rpc.connect(address, port)
        
        print("Available Rooms:", self.get_available_rooms())
        print(self.conn.root.exposed_getServerInfo())

        receive_thread = Thread(target=self.update_loop) 
        receive_thread.start()

        input_thread = Thread(target=self.input_loop) 
        input_thread.start()


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

    def get_messages(self):
        return self.conn.root.exposed_getMessages(self.name, self.room)

    def input_loop(self):
        sleep(.1)
        while True:
            cmd = input(" >").split(" ", 1)
            
            if cmd[0] == "a":
                self.send_message(cmd[1])

            elif cmd[0] == "u":
                self.name = cmd[1]
                print(F"Username set to {cmd[1]}")

            elif cmd[0] == "j":
                if self.join_room(cmd[1]):
                    print(F"joined {cmd[1]}")

            else:
                print(F"Unknown command: {cmd[0]}")

    def update_loop(self):
        rate = .5
        #os.system('clear')
        while True:

            newContent = self.get_messages()
            if newContent == self.lastContent:
                sleep(1/rate)
                continue
            
            #os.system('clear')
            count = 0
            print(F"in chatroom: {self.room} as {self.name}")
            for sender, msg in newContent:
                print(F"{count}) {sender}: {msg}")
                count += 1
            self.lastContent = newContent[-10:]
            sleep(1/rate)
        

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat client")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    parser.add_argument('-a', '--address', required=False, default="localhost", type=str)
    return parser.parse_args()

if __name__ == '__main__':
    args = get_args(sys.argv[1:])
    client = Client(args.address, args.port)