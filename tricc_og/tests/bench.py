# pip install simple_benchmark

from random import sample

def ForLoop(s):
    for e in s:
        break
    return e

def IterNext(s):
    return next(iter(s))

def ListIndex(s):
    return list(s)[0]

def PopAdd(s):
    e = s.pop()
    s.add(e)
    return e

def RandomSample(s):
    return sample(s, 1)

def SetUnpacking(s):
    e, *_ = s
    return e

from simple_benchmark import benchmark

b = benchmark([ForLoop, IterNext, ListIndex, PopAdd, RandomSample, SetUnpacking],
              {2**i: set(range(2**i)) for i in range(1, 20)},
              argument_name='set size',
              function_aliases={first: 'First'})

b.plot()