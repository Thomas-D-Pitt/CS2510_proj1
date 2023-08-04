import datetime, json

exampleDict = {1 : [datetime.datetime.now(), 1, 2]}
for key,value in exampleDict.items():
            exampleDict[key][0] = str(exampleDict[key][0])
print(exampleDict)

otherPendingProposals = json.dumps(exampleDict)

otherPendingProposals = dict(json.loads(otherPendingProposals))
for key, value in otherPendingProposals.items():
    otherPendingProposals[key] = [datetime.datetime.strptime(str(otherPendingProposals[key][0]), '%Y-%m-%d %H:%M:%S.%f')] + otherPendingProposals[key][1:]


print("finished", otherPendingProposals, type(otherPendingProposals))