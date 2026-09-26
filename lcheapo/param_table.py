# Exemple avec lists
params = [['8J', 'UP04', '2023-07-23T12', '2023-07-23T18', 1, 50, '3124567'],
          ['8J', 'UP04', '2023-08-23T12', '2023-08-23T18', 3, 40, '3124567'],
        ]
i=1
net=parms[i][0]
sta=params[i][1]
...

# Exemple avec dicts
params = {'UP04_3124567_pass1': ['8J', 'UP04', '2023-07-23T12', '2023-07-23T18', 1, 50, '3124567'],
          'UP04_3124567_pass2': ['8J', 'UP04', '2023-08-23T12', '2023-08-23T18', 3, 40, '3124567'],
        }
key='UP04_3124567_pass2'
net=parms[key][0]
sta=params[key][1]
...

# Et si vous declarez une dataclass...
from dataclass import dataclass

@dataclass
class CepsParams:
   net: str
   sta: str
   starttime: str
   endtime: str
   k: int
   l: int
   bateau: str
   
params = {'UP04_3124567_pass1': CepsParams('8J', 'UP04', '2023-07-23T12', '2023-07-23T18', 1, 50, '3124567'),
          'UP04_3124567_pass2': CepsParams('8J', 'UP04', '2023-08-23T12', '2023-08-23T18', 3, 40, '3124567'),
        }
key='UP04_3124567_pass2'
net=parms[key].net
sta=params[key].sta
starttime=UTCDateTime(params[key].starttime)
...