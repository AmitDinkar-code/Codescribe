"""A tiny demo store package used to exercise codescribe.

It deliberately contains a cyclic import (`order` <-> `customer`) so the
dependency-cycle detector has something to find.
"""
