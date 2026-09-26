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
import inspect
from pathlib import Path

from utils import assertTextFilesEqual


class TestLCHEAPOMethods(unittest.TestCase):
    """
    Test suite for nordic io operations.
    """
    def setUp(self):
        self.path = Path(inspect.getfile(
            inspect.currentframe())).resolve().parent
        self.test_path = self.path / "data"

    def test_lcinfo(self):
        """
        Test lcinfo
        """
        # Run the code
        cmd = f'lcinfo -d {self.path} -i data BUGGY.fix.lch > temp'
        system(cmd)

        # Compare text files
        assertTextFilesEqual(self, 'temp',
            str(Path(self.test_path) / 'BUGGY.info.txt'))
        Path('temp').unlink()


def suite():
    return unittest.makeSuite(TestLCHEAPOMethods, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
