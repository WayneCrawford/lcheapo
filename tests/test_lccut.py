#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Functions to test the lcheapo functions
"""
from os import system
import unittest
import inspect
from pathlib import Path

from utils import assertBinFilesEqual

class TestLCHEAPOMethods(unittest.TestCase):
    """
    Test suite for nordic io operations.
    """
    def setUp(self):
        self.path = Path(inspect.getfile(
            inspect.currentframe())).resolve().parent
        self.test_path = self.path / "data"

    def test_lccut(self):
        """
        Test lccut
        """
        # Run the code
        cmd = f'lccut -i data BUGGY.fix.lch --start 5000 --end 5099'
        system(cmd)
        # Path('temp').unlink()
        Path('process-steps.json').unlink()

        # Compare binary files (fix.timetears.txt)
        outfname = 'BUGGY.fix_5000_5099.lch'
        assert Path(outfname).exists()
        assertBinFilesEqual(self,  outfname, self.test_path / outfname)
        Path(outfname).unlink()


def suite():
    return unittest.makeSuite(TestLCHEAPOMethods, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
