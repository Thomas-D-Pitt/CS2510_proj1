import sys, argparse, os, json
import rpyc as rpc
from threading import Thread, Lock
from time import sleep, time
from rpyc.utils.server import ThreadedServer
import datetime
import pickle

DEBUG_MESSAGES = []

SERVER_ADDRESSES = {
    0 : "172.30.100.101:12000",
    1 : "172.30.100.102:12000",
    2 : "172.30.100.103:12000",
    3 : "172.30.100.104:12000",
    4 : "172.30.100.105:12000"
}

TIMEOUT = 1



class ResultCode():
    RESULT_CODE = {
        -1 : "unknown error",
        0 : "all good",
        1 : "requesting server is not leader",
        2 : "request number is incorrect",
        3 : "another request with the same number has already been proposed",
        4 : "server connection issue",
        5 : "no response"
        # 100 and up reserved
    }

    def __init__(self, value):
        for key in SERVER_ADDRESSES.keys():
            self.RESULT_CODE[100 + key] = F"current leader is server: {key}"

        self.value = value
    
    def __repr__(self) -> str:
        return F"{self.value}:{self.RESULT_CODE[self.value]}"


### Decorator function ###
def write_function(func):
    # Handles all of the additional code that should be run for each write to the server
    def inner(self, *args, **kwargs):
        
        if type(self) != Server:
            raise Exception("invalid use of write_function decorator")

        receivingServer = int(kwargs.pop('receivingServer', self.index))
        fromOwnLog = kwargs.pop('fromOwnLog', False)
        decided = kwargs.pop('decided', False)

        if not decided and receivingServer == self.index:
            cmdString = F"{receivingServer}|{self.vector_stamp[receivingServer] + 1}|{func.__name__}|{args}|{json.dumps(kwargs)}"
            print(F"Proposing: {cmdString}")
            returnVal = self.proposeCmd(cmdString, int(receivingServer))

            if type(returnVal) == ResultCode:
                if returnVal.value >= 100:
                    if self.adjustLeaderToMajority():
                        returnVal = self.proposeCmd(cmdString, int(receivingServer), secondPass=True)

            if type(returnVal) == ResultCode:
                return None
            return returnVal
        
        elif decided:
            self.vector_stamp[receivingServer] += 1
            if not fromOwnLog: # save command to disk
                event_stamp = self.vector_stamp[receivingServer]
                cmdString = F"{receivingServer}|{event_stamp}|{func.__name__}|{args}|{json.dumps(kwargs)}"
                with open(F"server{self.index}_log.txt", "a") as myfile:
                    myfile.write(cmdString + '\n')

                print(F"Write function Called: {receivingServer}|{event_stamp}|{func.__name__}|{args}|{json.dumps(kwargs)}")

                if receivingServer == self.index : # share cmd to all other servers
                    t = Thread(target = self.serverShareCmd, args = [cmdString], daemon=True)
                    t.start()

            return func(self, *args, **kwargs)
        
        else:
            raise Exception("invalid write function call")

    return inner

class Chatroom():
    
    def __init__(self, name):
        self.participants = []
        self.participantHeartbeats = {}
        self.messages = []
        self.name = name
        

        purge_thread = Thread(target=self.purge, daemon=True) 
        purge_thread.start()

    def purge(self):
        # Removes inactive users from chatroom as determined by last heartbeat
        timeout = 1
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
            self.participants.remove(username)
            return True
        return False

    def newMessage(self, user, message, timestamp, messageid):
        timestamp = datetime.datetime.strptime(str(timestamp), '%Y-%m-%d %H:%M:%S.%f')

        data = [messageid, user, message, [], timestamp]
        done = False
        # insert in order
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
        msg = self.getMessageByID(messageid)
        for i in range(len(msg[3])):
            cUser, cTimestamp, cVal = msg[3][i]

            if user == cUser:
                if cVal == value: # overwritting existing like with newer timestamp
                    msg[3][i] = (user, timestamp, value)
                    return False

                elif cVal != value: # prior removed like
                    if cTimestamp < timestamp: # new like is more recent than removal
                        msg[3][i] = (user, timestamp, value)
                        return True
                    else:
                        return False

        msg[3].append((user, timestamp, value))
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
    
    def getMessageByID(self, id):
        for message in self.messages:
            if message[0] == id:
                return message

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
        self.clients_on_other_servers = [[] for _ in range(len(SERVER_ADDRESSES.keys()))]
        self.hidden_clients = [[] for _ in range(len(SERVER_ADDRESSES.keys()))]
        self.my_clients = []
        self.current_leader = 0
        self.pendingProposals = {}
        self.pendingNewLeader = None
        self.proposalLock = Lock()

        for key in SERVER_ADDRESSES.keys():
            self.messagesToProcess[key] = []

        if os.path.isfile(F"server{self.index}_log.txt"):
            t = Thread(target=self.recoverFromCrash)
            t.start()

        for key in SERVER_ADDRESSES.keys():
            t = Thread(target=self.anti_entropy, args=[key])
            t.start()
            

        receive_thread = Thread(target=self.update_loop, daemon=True) 
        receive_thread.start()
        

    def recoverFromCrash(self):
        sleep(0.1)
        
        self.adjustLeaderToMajority()

        try:
            # rerun all commands in log file
            if os.path.isfile(F"server{self.index}_log.txt"):
                with open(F"server{self.index}_log.txt", "r") as myfile:
                    msgs = myfile.readlines()

                for msg in msgs:
                    self.processCmdString(msg.replace('\n', ''), fromOwnLog=True)
                    

            
            self.serverDataGet(self.current_leader)

            

            # restore all hidden clients
            if os.path.isfile(F"Server_{self.index}_hidden_clients.pickle"):
                with open(F"Server_{self.index}_hidden_clients.pickle", 'rb') as f:
                    self.hidden_clients = pickle.load(f)

            # run a leave event for all clients that were connected at time of crash so other servers know they are not partitioned/coming back
            if os.path.isfile(F"Server_{self.index}_clients.pickle"):
                with LOCK:
                    with open(F"Server_{self.index}_clients.pickle", 'rb') as f:
                        
                        self.my_clients = pickle.load(f)
                        print("my clients:", self.my_clients)
                    
                    for user, roomName in self.my_clients:
                        self.leave(user, roomName, datetime.datetime.now())

                    self.my_clients = []

            sleep(1)
            print("cahtroom participants...")
            for cr in self.chatrooms:
                print(cr.participants)

            print("Recovered from crash, vector_stamp:", self.vector_stamp)

        except Exception as e: 
            # in the event of a failure allow the server to continue running rather than an immediate crash
            print(F"Error occured while recovering from crash:", e)

    def serverDataGet(self, otherServerIndex, requireLock = True):
        global LOCK
        # get all unknown information from another server
        if otherServerIndex != self.index:
            address, port = SERVER_ADDRESSES[otherServerIndex].split(":", 1)
            conn = rpc.connect(address, port)

            newMessages, otherPendingProposals = conn.root.exposed_getServerData(self.vector_stamp)
            otherPendingProposals = dict(json.loads(otherPendingProposals))
            for key, value in otherPendingProposals.items():
                otherPendingProposals[key] = [datetime.datetime.strptime(str(otherPendingProposals[key][0]), '%Y-%m-%d %H:%M:%S.%f')] + otherPendingProposals[key][1:]

            if requireLock:
                with LOCK:
                    for message in newMessages:
                        self.processCmdString(message)
            else:
                for message in newMessages:
                        self.processCmdString(message)

            for key, value in otherPendingProposals.items():
                if key not in self.pendingProposals:
                    self.pendingProposals[key] = value


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

        pendingProposals = self.pendingProposals
        for key,value in pendingProposals.items(): # prepare data from sending
            pendingProposals[key][0] = str(pendingProposals[key][0])

        returnVal = (filtered_msgs, json.dumps(pendingProposals))

        for key,value in pendingProposals.items(): # return data to previous state
            pendingProposals[key][0] = datetime.datetime.strptime(str(pendingProposals[key][0]), '%Y-%m-%d %H:%M:%S.%f')

        return returnVal

    def serverShareCmd(self, cmd, proposalID = None, existingConn = None, connServer = None):
        for key, value in SERVER_ADDRESSES.items():
            t = Thread(target = self._serverShareCmdHelper, args = [key, value, cmd, proposalID, existingConn, connServer])
            t.start()

    def _serverShareCmdHelper(self, key, value, cmd, proposalID = None, existingConn = None, connServer = None):
        try:
            if key == self.index: return
            if connServer and existingConn and existingConn == key:
                print("_serverShareCmdHelper existingConn", connServer)
                existingConn.root.exposed_processCmdString(cmd, proposalID = proposalID, withLock = False)
            else:
                address, port = value.split(":", 1)
                conn = rpc.connect(address, port)
                conn.root.exposed_processCmdString(cmd, proposalID = proposalID)
                conn.close()
        except Exception as e:
            print(F"Error in serverShareCmd on {key}: {e}")

    def proposeCmd(self, cmd, receivingServer, conn = None, secondPass = False):
        proposeAgain = False
        with self.proposalLock:

            if secondPass: # the requesting server has asked all other servers who the majority leader is and is asking again
                print("proposing again")
                self.adjustLeaderToMajority()

            if self.current_leader == self.index: # share to other servers
                print(F"Sharing propose : {cmd}")
                resultsLock = Lock()
                results = [-1 for key in SERVER_ADDRESSES.keys()]
                for key, value in SERVER_ADDRESSES.items():
                    t = Thread(target = self.proposeCmdShare, args = [key, sum(self.vector_stamp) + 1, cmd, self.index, results, resultsLock, conn, receivingServer])
                    t.start()

                for i in range(10):
                    accepted_servers = 0
                    failed_servers = 0
                    notLeaderresults = 0
                    with resultsLock:
                        for result in results:
                            if type(result) == ResultCode and result.value == 0:
                                accepted_servers += 1

                            elif type(result) == ResultCode and result.value == 1: # server is no longer leader
                                notLeaderresults += 1

                            elif type(result) == ResultCode and result.value > 0:
                                failed_servers += 1

                        
                    if accepted_servers > len(SERVER_ADDRESSES.keys()) / 2:
                        print("proposal passes")
                        self.serverShareCmd(cmd, proposalID=sum(self.vector_stamp) + 1, existingConn = conn, connServer=receivingServer)
                        return self.processCmdString(cmd, proposalID=sum(self.vector_stamp) + 1)
                    
                    elif failed_servers > len(SERVER_ADDRESSES.keys()) / 2:
                        print(F"propose failed: {results}")
                        return None
                    
                    elif receivingServer == self.index and notLeaderresults > len(SERVER_ADDRESSES.keys()) / 2:
                        print(F"propose failed: {results}")
                        proposeAgain = True if secondPass == False else False # adjust to new leader and propose

                    elif receivingServer != self.index and notLeaderresults > len(SERVER_ADDRESSES.keys()) / 2:
                        print(F"propose failed: {results}")
                        return ResultCode(1)

                    sleep(TIMEOUT / 10)
                print(F"propose timed out, results: {results}")
                if receivingServer == self.index:
                    return None
                else:
                    return ResultCode(4)
                

            elif receivingServer == self.index: # have leader share with other servers
                
                try:
                    print(F"propose to leader {self.current_leader}: {cmd}".replace('\n', ''))
                    resultsLock = Lock()
                    results = [] # easiest way to pass variable by reference rather than value
                    returnVal = None
                    t = Thread(target = self._proposeCmdHelper, args = [cmd, receivingServer, results, resultsLock], kwargs={"secondPass":secondPass})
                    t.start()
                    for i in range(10):
                        with resultsLock:
                            if len(results) > 0:
                                returnVal = results[0]
                                break
                        sleep(TIMEOUT/10)
                    
                    

                    if len(results) == 0:
                        raise Exception("no response within timeout")
                    
                    elif type(returnVal) == ResultCode and returnVal.value == 1:
                        # asking server that is not leader
                        proposeAgain = True if secondPass == False else False

                    elif type(returnVal) == ResultCode and returnVal.value == 4:
                        # asking server that is not leader
                        return None

                    return returnVal
                except Exception as e:
                    print(F"failed to propose to leader {self.current_leader}: {e}, holding election")
                    if self.becomeLeader():
                        proposeAgain = True if secondPass == False else False
                        


            
            else:
                return ResultCode(100 + self.current_leader)
            
        if proposeAgain:
            return self.proposeCmd(cmd, receivingServer, conn, secondPass=True)
        
    def _proposeCmdHelper(self, cmd, receivingServer, results, resultsLock, secondPass = False):
        address, port = SERVER_ADDRESSES[self.current_leader].split(":", 1)
        conn = rpc.connect(address, port, service=Connection)

        returnVal = -1
        try:
            returnVal = conn.root.exposed_proposeCmd(cmd, receivingServer, secondPass=secondPass)

        finally:
            with resultsLock:
                if returnVal != -1:
                    results.append(returnVal)
            conn.close() 

        return returnVal
        
    def proposeCmdShare(self, targetServer, requestNum, cmd, requestingServer, results, resultsLock, ExistingConn, initiatingServer):
        if targetServer != self.index:
            address, port = SERVER_ADDRESSES[targetServer].split(":", 1)
            print(F"address, port: {address, port}")
            try:
                if targetServer != initiatingServer:
                    conn = rpc.connect(address, port)
                    returnVal = conn.root.exposed_recieiveProposal(requestNum, cmd, requestingServer)
                    returnVal = ResultCode(returnVal) # store value in local copy so that connection can be closed
                    conn.close()
                else:
                    print("exisiting conn:", type(ExistingConn))
                    returnVal = ExistingConn.root.exposed_recieiveProposal(requestNum, cmd, requestingServer, withLock=False)
                    returnVal = ResultCode(returnVal)
                    print("exisiting conn done")
            except Exception as e:
                print("proposeCmdShare error:", e)
                returnVal = ResultCode(4)
            

        else:
            returnVal = self.recieiveProposal(requestNum, cmd, requestingServer)
            returnVal = ResultCode(returnVal)

        with resultsLock:
            results[targetServer] = returnVal

        return returnVal

    def recieiveProposal(self, requestNum, cmd, requestingServer):
        # returns a ResultCode enum

        print(F"recived proposal: {cmd}")
        if requestNum > sum(self.vector_stamp) + 1:
            self.serverDataGet(requestingServer, requireLock=False)
        
        if requestingServer != self.current_leader:
            returnVal = 1 #ResultCode(1)
        
        elif requestNum <= sum(self.vector_stamp):
            returnVal = 2 #ResultCode(2)

        elif requestNum in self.pendingProposals and (datetime.datetime.now() - self.pendingProposals[requestNum][0]).total_seconds() < 1:
            returnVal = 3 #ResultCode(3)

        else:
            self.pendingProposals[requestNum] = [datetime.datetime.now(), requestingServer]
            returnVal = 0 #ResultCode(0)

        return returnVal

    def becomeLeader(self):
        resultsLock = Lock()
        results = [0 for key in SERVER_ADDRESSES.keys()]
        for i in SERVER_ADDRESSES.keys():
            t = Thread(target = self._becomeLeaderHelperPropose, args = [i, results, resultsLock])
            t.start()
        
        for i in range(20):
            with resultsLock:
                if sum(results) > len(SERVER_ADDRESSES.keys()) / 2:
                    print("election results (pass):", results)
                    for i in SERVER_ADDRESSES.keys():
                        t = Thread(target = self._becomeLeaderHelperElect, args = [i])
                        t.start()
                    return True
            sleep(TIMEOUT/10)

        print("election results (fail):", results)
        return False

    def _becomeLeaderHelperPropose(self, serverIndex, results, resultsLock):
        address, port = SERVER_ADDRESSES[serverIndex].split(":", 1)
        try:
            if serverIndex == self.index:
                proposalAccepted = self.newLeaderProposal(None, self.index)
            else:
                conn = rpc.connect(address, port)
                proposalAccepted = conn.root.exposed_newLeaderProposal(self.index)
                conn.close()
            
            if proposalAccepted:
                self.serverDataGet(serverIndex, requireLock = False)
                with resultsLock:
                    results[serverIndex] = 1
                return True
            else:
                print("election rejected on server:", serverIndex)
                raise Exception("Proposal rejected")

        except Exception as e:
            print(F"proposal failed in server: {serverIndex}, with error: {e}")
            return False
        
    def _becomeLeaderHelperElect(self, serverIndex):
        address, port = SERVER_ADDRESSES[serverIndex].split(":", 1)

        try:
            if serverIndex == self.index:
                self.newLeaderElected(None, self.index)
            else:
                conn = rpc.connect(address, port)
                conn.root.exposed_newLederElected(self.index)
                conn.close()

        except Exception as e:
            print(F"elect failed in server: {serverIndex}, with error: {e}")
            return False
        
    def newLeaderProposal(self, conn, newLeaderIndex):
        print("newLeaderProposal:", newLeaderIndex)
        now = datetime.datetime.now()
        if self.pendingNewLeader == None or (now - self.pendingNewLeader[0]).total_seconds() > TIMEOUT * 2 or self.pendingNewLeader[1] == newLeaderIndex:
            self.pendingNewLeader = (now, newLeaderIndex)
            return True
        
        return False
    
    def newLeaderElected(self, conn, newLeaderIndex):
        print("new leader elected:", newLeaderIndex)
        self.current_leader = newLeaderIndex

    def adjustLeaderToMajority(self):
        print("adjustLeaderToMajority")
        returnVal = False
        resultsLock = Lock()
        results = [-1 for key in SERVER_ADDRESSES.keys()]
        for i in SERVER_ADDRESSES.keys():
            t = Thread(target = self._adjustLeaderToMajorityHelper, args = [i, results, resultsLock])
            t.start()

        for _ in range(10):
            with resultsLock:
                for i in range(len(results)):
                    sum = 0
                    for j in range(i, len(results)):
                        
                        if results[i] == results[j] and results[i] != -1:
                            sum += 1

                    if sum > len(results) / 2: # the majority of servers think server:{i} is the leader
                        self.current_leader = i
                        print("adjustLeaderToMajority set new leader:", i)
                        returnVal = True
                        break
            if returnVal:
                break
            else:
                sleep(TIMEOUT/10)

        if not returnVal:       
            print("adjustLeaderToMajority could not determine leader")
        print("adjustLeaderToMajority completed")
        return returnVal

    def _adjustLeaderToMajorityHelper(self, serverIndex, results, resultsLock):
        address, port = SERVER_ADDRESSES[serverIndex].split(":", 1)

        try:
            conn = rpc.connect(address, port)
            leader = conn.root.exposed_getLeader()
            conn.close()

            with resultsLock:
                results[serverIndex] = leader
            return leader

        except Exception as e:
            print(F"getLeader failed in server: {serverIndex}, with error: {e}")
            return -1

    def processCmdString(self, cmd, fromOwnLog = False, depth = 0, proposalID = None):
        print("processing cmd string", cmd)
        # run an RPC that was stored to a string
        receivingServer, event_stamp, func, args, kwargs = cmd.replace("\n", "").split("|")
        #only run if it is the next command for a given server, otherwise save it for later
        if int(event_stamp) == self.vector_stamp[int(receivingServer)] + 1:

            if proposalID:
                self.pendingProposals.pop(proposalID)

            args = eval(args)
            kwargs = json.loads(kwargs)
            kwargs['decided'] = True

            func = getattr(self, func)
            
            

            if func == self.join:
                _ = kwargs.pop('otherServer', None)
                self.clients_on_other_servers[int(receivingServer)].append((args[0], args[1]))
                returnVal = func(*args, **kwargs, otherServer = int(receivingServer), receivingServer = receivingServer, fromOwnLog = fromOwnLog)

            elif func == self.leave:
                _ = kwargs.pop('otherServer', None)
                if (args[0], args[1]) in self.clients_on_other_servers[int(receivingServer)]:
                    self.clients_on_other_servers[int(receivingServer)].remove((args[0], args[1]))
                returnVal = func(*args, **kwargs, otherServer = int(receivingServer), receivingServer = receivingServer, fromOwnLog = fromOwnLog)
            else:
                returnVal = func(*args, **kwargs, receivingServer = receivingServer, fromOwnLog = fromOwnLog)

            messagesToStillProcess = []
            messagesToProcess = self.messagesToProcess
            for message in messagesToProcess[int(receivingServer)]:
                # try and run other commands waiting to be processed
                self.messagesToProcess[int(receivingServer)].remove(message)
                if not self.processCmdString(message, depth = depth+1):
                    messagesToStillProcess.append(message)

            self.messagesToProcess[int(receivingServer)] = messagesToStillProcess

            return returnVal

        else:
            self.messagesToProcess[int(receivingServer)].append(cmd)
            return None

    def anti_entropy(self, key):
        # get and process data from other servers
        sleep(1)
        while True:
            try:
                self.serverDataGet(key)
                # re-add all users where were removed due to loss of connection
                with LOCK:
                    if len(self.hidden_clients[key]) != 0:
                        print(f"adding clients from key {key}:", list(set(self.hidden_clients[key])))
                        for user, roomName in list(set(self.hidden_clients[int(key)])):
                            room = self.getRoom(roomName)
                            room.add_chatter(user)
                            
                        self.hidden_clients[key] = []
                        with open(F"Server_{self.index}_hidden_clients.pickle", 'wb') as f:
                            pickle.dump(self.hidden_clients, f)

            except Exception as e:
                print(F"Error in anti-entropy on {key}: {e}")
                # remove users who are connected to unreachable servers, store in a list to re-add if server reconnects
                with LOCK:
                    for user, roomName in self.clients_on_other_servers[int(key)]:
                        self.hidden_clients[int(key)].append((user, roomName))
                        self.hidden_clients[int(key)] = list(set(self.hidden_clients[int(key)])) # remove duplicates
                        with open(F"Server_{self.index}_hidden_clients.pickle", 'wb') as f: # save to disk in case of crash
                            pickle.dump(self.hidden_clients, f)
                        room = self.getRoom(roomName)
                        room.remove_chatter(user)


            sleep(1)

    def getRoom(self, roomName):
        if roomName == None: return None

        for room in self.chatrooms:
            if room.name == roomName:
                return room

        return None

    @write_function
    def join(self, user, roomName, timeStamp = None, otherServer = None):
        # adds user to chatroom, or creates chatroom if it does not exist 
        

        if user == None:
            return False
        
        if otherServer == None or otherServer == self.index:
            self.my_clients.append((user, roomName)) # keeps track of clients on disk in case of server crash
            with open(F"Server_{self.index}_clients.pickle", 'wb') as f:
                pickle.dump(self.my_clients, f)

        room = self.getRoom(roomName)
        if room:
            return room.add_chatter(user)
        
        newRoom = Chatroom(roomName)
        self.chatrooms.append(newRoom)
        
        return newRoom.add_chatter(user)

    @write_function
    def leave(self, user, roomName, timeStamp = None, otherServer = False):
        if user == None:
            return False
        
        for key in SERVER_ADDRESSES.keys(): # if leaving user is in hidden_users list remove them from the list
            if (user, roomName) in self.hidden_clients[int(key)]:
                self.hidden_clients[int(key)].remove((user, roomName))
                with open(F"Server_{self.index}_hidden_clients.pickle", 'wb') as f:
                    pickle.dump(self.hidden_clients, f)

        room = self.getRoom(roomName)
        if room :
            if otherServer == None or otherServer == self.index:
                print(F"REMOVING:", user, roomName)
                if (user, roomName) in self.my_clients:
                    self.my_clients.remove((user, roomName)) # keeps track of clients on disk in case of server crash
                print(F"REMOVING2:", user, roomName)
                with open(F"Server_{self.index}_clients.pickle", 'wb') as f:
                    print(F"REMOVING3:", user, roomName)
                    pickle.dump(self.my_clients, f)
            print(F"REMOVING4:", user, roomName)
            returnVal = room.remove_chatter(user)
            print(F"REMOVAL:", returnVal)
            return room.remove_chatter(user)

        return False

    def availableRooms(self):
        return [room.name for room in self.chatrooms]
    
    def reachableServers(self):
        # returns a boolean vector defining reachability of each server
        # reachable defined as got a response within 1 second
        resultVector = [False for key in SERVER_ADDRESSES.keys()]
        lock = Lock()
        for key in SERVER_ADDRESSES.keys():
            t = Thread(target = self.checkConnection, args = [key, resultVector, lock])
            t.start()

        sleep(1)
        return resultVector

    def checkConnection(self, serverid, resultVector = None, lock = None):
        # check if the server is able to reach server: serverid
        # if a resultVector is given then result is also stored in vector
        if serverid == self.index:
            returnval = True
        
        else:

            address, port = SERVER_ADDRESSES[serverid].split(":", 1)
            conn = rpc.connect(address, port)

            try:
                conn.root.availableRooms()
                returnval = True

            except:
                returnval = False

            conn.close()

        if resultVector:
            if lock:
                with lock:
                    resultVector[serverid] = returnval

            else:
                resultVector[serverid] = returnval

        return returnval

# newMessage, getMessages, getChatters, likeMessage, and unlikeMessage simply pass arguments on to the appropriate chatroom
    @write_function
    def newMessage(self, user, roomName, message, timeStamp, messageid):
        room = self.getRoom(roomName)
        if room and (user in room.participants or self.isHiddenUser(user, roomName)):
            room.newMessage(user, message, timeStamp, messageid)
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
        if room and (user in room.participants or self.isHiddenUser(user, roomName)):
            return room.likeMessage(user, messageid, timeStamp)
        else:
            return False

    @write_function
    def unlikeMessage(self, user, roomName, messageid, timeStamp):
        room = self.getRoom(roomName)
        if room and (user in room.participants or self.isHiddenUser(user, roomName)):
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

    def isHiddenUser(self, user, roomName):
        # is the user in roomName in the hidden_users list
        for srv in self.hidden_clients:
            for tuser, troomName in srv:
                if user == tuser and roomName == troomName:
                    return True
            
        return False

class Connection(rpc.Service):
    """
    Manages forwarding RPCs to server object shared across all connections
    """
    def on_connect(self, conn):
        self.clientName = None
        self.clientRoom = None
        self.conn = conn

    def on_disconnect(self, conn):
        if self.clientName and self.clientRoom:
            try:
                SERVER.leave(self.clientName, self.clientRoom, datetime.datetime.now())
            except Exception as e:
                print(F'attempted to remove {self.clientName} from {self.clientRoom} but failed eith exception: {e}')

    def exposed_getLeader(self):
        return SERVER.current_leader

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
            val = SERVER.newMessage(*args, messageid=F"{SERVER.index}_{SERVER.vector_stamp[SERVER.index]}", **kwargs)

        return val



    def exposed_availableRooms(self, *args, **kwargs):

        global SERVER, LOCK
        with LOCK:
            val = SERVER.availableRooms(*args, **kwargs)

        return val



    def exposed_join(self, *args, **kwargs):

        global SERVER, LOCK, START_TIME
        if (datetime.datetime.now() - START_TIME).total_seconds() < 3:
            return -2
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
        #with LOCK:
        val = str(SERVER)

        return val
    
    def exposed_proposeCmd(self, *args, **kwargs):

        global SERVER

        val = SERVER.proposeCmd(*args, conn = self.conn, **kwargs)

        return val


    def exposed_getServerData(self, *args, **kwargs):

        global SERVER
        with LOCK:
            val = SERVER.serverDataGive(*args, **kwargs)

        return val

    def exposed_processCmdString(self, *args, **kwargs):
        withLock = kwargs.pop("withLock", True)
        global SERVER
        if withLock:
            with LOCK:
                val = SERVER.processCmdString(*args, **kwargs)
        else:
            val = SERVER.processCmdString(*args, **kwargs)

        return val
    
    def exposed_reachableServers(self, *args, **kwargs):
        global SERVER
        return SERVER.reachableServers(*args, **kwargs)
    
    def exposed_recieiveProposal(self, *args, **kwargs):
        withLock = kwargs.pop("withLock", True)
        global SERVER
        if withLock:
            with LOCK:
                val = SERVER.recieiveProposal(*args, **kwargs)
        else:
            val = SERVER.recieiveProposal(*args, **kwargs)

        return val
    
    def exposed_newLeaderProposal(*args, **kwargs):
        global SERVER
        with LOCK:
            val = SERVER.newLeaderProposal(*args, **kwargs)
        return val
    
    def exposed_newLederElected(*args, **kwargs):
        global SERVER
        with LOCK:
            val = SERVER.newLeaderElected(*args, **kwargs)
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
    START_TIME = datetime.datetime.now()
    connectionHandler = ThreadedServer(Connection, port = args.port, listener_timeout=2)
    connectionHandler.start()