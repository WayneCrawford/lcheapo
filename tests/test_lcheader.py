#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Functions to test the lcheapo functions
"""
from os import system
import unittest
import inspect
from pathlib import Path

from utils import assertBinFilesEqual, assertTextFilesEqual


class TestLCHEAPOMethods(unittest.TestCase):
    """
    Test suite for nordic io operations.
    """
    def setUp(self):
        self.path = Path(inspect.getfile(
            inspect.currentframe())).resolve().parent
        self.test_path = self.path / "data"

    def test_lcheader(self):
        """
        Test lcheader
        """
        # Run the code without any questions
        cmd = 'lcheader --no_questions'
        system(cmd)

        outfname = 'generic.header.lch'
        # Check that the appropriate file was created
        assert Path(outfname).exists(), 'generic.header.lch not found'

        # Compare output binary file (fix.lch)
        assertBinFilesEqual(self, outfname, self.test_path / outfname)
        Path(outfname).unlink()
        Path('process-steps.json').unlink()

        # Run the code with all specified
        cmd = f'lcheader --description MOMARL_SPOBS2_04_LSVEL -s 62.5 -c 4 -w 2019-02-04T04:53:30.024 -e 2019-06-14T04:04:29 --output_file LSVEL.header.lch > LSVEL.txt'
        system(cmd)
        outfname = 'LSVEL.header.lch'
        assert Path(outfname).exists()
        assertBinFilesEqual(self, outfname, self.test_path / outfname)
        Path(outfname).unlink()
        outfname = 'LSVEL.txt'
        assertTextFilesEqual(self, outfname, self.test_path / outfname)
        Path(outfname).unlink()
        Path('process-steps.json').unlink()


def suite():
    return unittest.makeSuite(TestLCHEAPOMethods, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
