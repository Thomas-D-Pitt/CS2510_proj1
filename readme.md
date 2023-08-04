# CS 2510: Project 1

## Changes to test_p2
changed run command to use python, and added -itd argument for the cmd_str in init_containers (so that containers show output in log)

## Setup

To build the image, run:
```
docker build . -t "cs2510_fp"
```

The servers can the be started using 
```
python3 test_p2.py init
```

To run a container using this image, you can run:
```
docker run --cap-add=NET_ADMIN -it --name cs2510_client1 --network cs2510 --ip 172.30.100.111 cs2510_fp python3 client.py
```
This command will create a docker image and start the client on it
Additional clients can be created with the same command but a different name and ip ex:
```
docker run --cap-add=NET_ADMIN -it --name cs2510_client2 --network cs2510 --ip 172.30.100.112 cs2510_fp python3 client.py
```

Clients that automatically send messages and log latency can be created with the following command:
```
docker run --cap-add=NET_ADMIN -it --name cs2510_client3 --network cs2510 --ip 172.30.100.113 cs2510_fp python3 clientAuto.py --id 3
```
Note that these clients should also be given a unique name, ip, and id argument. The latency log can be found by using the docker client to look at the continers files. The log is located in app/cs2510_fp/client3_log.txt. The graphs used in my report were generated using latencyPlot.py

When you are done, clean up with:
```
python3 test_p2.py rm
```

## Client Commands
The first command must be
```
c <server_id (1-5)>
```

after connecting to a server you will see some information about the group and participants, these will be None until you connect to a chatroom. 

the next command you must run is 
```
u <name>
```
This will set your name and allow you to join chatrooms using 
```
j <room name>
```
After setting a name and joining a chatroom you may use the following commands

add message:
```
a <message content>
```
like message:
```
l <message number>
```
remove like from message:
```
r <message number>
```
print chat history:
```
p
```
quit program:
```
q
```
change name (leaves chatroom):
```
u <name>
```
change room:
```
j <room name>
```
check reachable servers (for current server):
```
v
```
