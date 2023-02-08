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


        self.name = "tom"
        self.join_room("test")
        print("Available Rooms:", self.get_available_rooms())
        self.send_message("hello world")
        
        receive_thread = Thread(target=self.update_loop) 
        receive_thread.start()


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
        pass

    def update_loop(self):
        count = 0
        while True:
            count += 1
            self.send_message(F"hello world{count}")

            newContent = self.get_messages()
            if newContent == self.lastContent:
                return
            
            os.system('clear')
            for sender, msg in newContent:
                print(F"{sender}: {msg}")
            self.lastContent = newContent[-10:]
            sleep(1)
        

def get_args(argv):
    parser = argparse.ArgumentParser(description="chat client")
    parser.add_argument('-p', '--port', required=False, default=12000, type=int)
    parser.add_argument('-a', '--address', required=False, default="localhost", type=str)
    return parser.parse_args()

if __name__ == '__main__':
    args = get_args(sys.argv[1:])
    client = Client(args.address, args.port)