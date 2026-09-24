"""Portable single-component names, including on case-insensitive filesystems."""
import re

_DEVICES = {'con', 'prn', 'aux', 'nul'} | {
    prefix + str(number) for prefix in ('com', 'lpt') for number in range(1, 10)
}


def portable_name(name):
    return (isinstance(name, str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]+', name))
            and name not in {'.', '..'} and not name.endswith('.')
            and name.split('.')[0].casefold() not in _DEVICES)
