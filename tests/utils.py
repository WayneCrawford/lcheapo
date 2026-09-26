#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utility functions for the lcheapo tests
"""
import filecmp
import difflib
import json


def assertProcessStepsFilesEqual(obj, first, second, msg=None):
    with open(first, "r") as fp:
        first_tree = json.load(fp)
        first_tree = _remove_changeable_processes(first_tree)
    with open(second, "r") as fp:
        second_tree = json.load(fp)
        second_tree = _remove_changeable_processes(second_tree)
    obj.maxDiff = None
    obj.assertEqual(first_tree, second_tree)

def _remove_changeable_processes(tree):
    for step in tree["steps"]:
        step["application"].pop("version", None)
        step["execution"].pop("date", None)
        step["execution"].pop("commandline", None)
        step["execution"]["parameters"].pop("base_directory", None)
        step["execution"]["parameters"].pop("output_directory", None)
        step["execution"]["parameters"].pop("input_directory", None)
    return tree

def assertTextFilesEqual(obj, first, second, msg=None):
    with open(first) as f:
        str_a = f.read()
    with open(second) as f:
        str_b = f.read()

    if str_a != str_b:
        first_lines = str_a.splitlines(True)
        second_lines = str_b.splitlines(True)
        delta = difflib.unified_diff(
            first_lines, second_lines,
            fromfile=first, tofile=second)
        message = ''.join(delta)

        if msg:
            message += " : " + msg

        obj.fail("Multi-line strings are unequal:\n" + message)

def assertBinFilesEqual(obj, first, second, msg=None):
    """ Compares two binary files """
    obj.assertTrue(filecmp.cmp(first, second))

