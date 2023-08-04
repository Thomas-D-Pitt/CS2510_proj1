import matplotlib.pyplot as plt
import datetime

#files = ["client1_log_many.txt", "client2_log_many.txt", "client3_log_many.txt"]
files = ["client2_log_leader_killed.txt"]
styles = ['o-r', 'o-g', 'o-b']

def parse(filename):
    with open(filename, "r") as myfile:
        lines = myfile.readlines()
    x = []
    y = []
    for line in lines:
        parts = line.replace('\n', '').split(', ')
        timestamp1 = datetime.datetime.strptime(str(parts[0]), '%Y-%m-%d %H:%M:%S.%f')
        timestamp2 = datetime.datetime.strptime(str(parts[1]), '%Y-%m-%d %H:%M:%S.%f')
        x.append(timestamp1)
        y.append((timestamp2 - timestamp1).total_seconds() * 100)

    return x, y

for i in range(len(files)):
    x, y = parse(files[i])
    plt.plot(x, y, styles[i])

plt.show()