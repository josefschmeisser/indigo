import numpy as np
import collections

Scenario = collections.namedtuple('Scenario', 'bw delay woker_0 worker_1 woker_2 woker_3 woker_4')
Person = collections.namedtuple('Person', 'name age gender')

print 'Type of Person:', type(Person)

bob = Person(name='Bob', age=30, gender='male')
print '\nRepresentation:', bob


def obtain_scenario():
    np.linspace(10, 200)
    pass
