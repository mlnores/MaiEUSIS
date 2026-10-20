"""Shared record primitives, independent of any task model."""
import math
import re

STATUSES = {'known','unknown','assumed','inferred','contested','probable','low-confidence','source-dependent','requires-verification'}
ACTIONS = {'ask','challenge','support','explain','compare','highlight-dependency','request-evidence','advise','silence'}
CONDITIONS = {'A','B','C','D','E','F'}

class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:raise ValidationError(message)


def fields(data, required, optional=()):
    require(isinstance(data,dict),'Expected an object')
    require(set(required)<=data.keys(),f'Missing fields: {sorted(set(required)-data.keys())}')
    require(not data.keys()-set(required)-set(optional),f'Forbidden or unrecognized fields: {sorted(data.keys()-set(required)-set(optional))}')


def number(x, low=-1e9, high=1e9):
    return type(x) in (int,float) and math.isfinite(x) and low<=x<=high


def identity(x):
    return isinstance(x,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',x))


