#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Functions to test the lcheapo functions
"""
# from __future__ import (absolute_import, division, print_function,
#                         unicode_literals)
# from future.builtins import *  # NOQA @UnusedWildImport

from os import system
import unittest
import filecmp
import inspect
import difflib
import json
from pathlib import Path

from utils import assertTextFilesEqual


class TestLCHEAPOMethods(unittest.TestCase):
    """
    Test suite.
    """
    def setUp(self):
        self.path = Path(inspect.getfile(
            inspect.currentframe())).resolve().parent
        self.test_path = self.path / "data"

    def test_lcdump(self):
        """
        Test lcdump outputs.
        """
        # WRITEOUT OF DATA HEADERS
        cmd = f'lcdump {Path(self.test_path) / "BUGGY.raw.lch"} 5000 100  > temp_test.out'
        system(cmd)
        assertTextFilesEqual(self, 'temp_test.out',
                             self.test_path / 'BUGGY_lcdump_5000_100.txt')
        Path('temp_test.out').unlink()

        # WRITEOUT OF FILE HEADER

        # WRITEOUT OF DIRECTORY


def suite():
    return unittest.makeSuite(TestLCHEAPOMethods, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
