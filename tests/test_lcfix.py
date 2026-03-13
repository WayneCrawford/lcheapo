#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test the lcheapo functions
"""
from os import system
import unittest
import inspect
from pathlib import Path

from utils import (assertBinFilesEqual, assertTextFilesEqual,
                    assertProcessStepsFilesEqual)


class TestLCHEAPOMethods(unittest.TestCase):
    """
    Test suite
    """
    def setUp(self):
        self.path = Path(inspect.getfile(
            inspect.currentframe())).resolve().parent
        self.test_path = self.path / "data"

    def test_lcfix_buggy(self):
        """
        Test lcfix on a typical (buggy) file
        """
        # Run the code
        cmd = f'lcfix -d {self.path} -i data BUGGY.raw.lch > temp_buggy'
        system(cmd)
        Path('temp_buggy').unlink()

        # Check that the appropriate files were created
        assert not Path('BUGGY.fix.timetears.txt').exists()

        # Compare binary files (fix.lch)
        outfname = 'BUGGY.fix.lch'
        assert Path(outfname).exists()
        assertBinFilesEqual(self, outfname, str(self.test_path / outfname))
        Path(outfname).unlink()

        # Compare text files (fix.txt)
        outfname = 'BUGGY.fix.txt'
        assert Path(outfname).exists()
        assertTextFilesEqual(self,  outfname, str(self.test_path / outfname))
        Path(outfname).unlink()

        # Compare text files (process-steps.json)
        outfname = 'process-steps.json'
        assert Path(outfname).exists()
        new_outfname = 'BUGGY.' + outfname
        Path(outfname).rename(new_outfname)
        assertProcessStepsFilesEqual(self, new_outfname,
                                     str(self.test_path / new_outfname))
        Path(new_outfname).unlink()

    def test_lcfix_bad(self):
        """
        Test lcfix on a bad (full of time tears) file
        """
        # Run the code
        cmd = f'lcfix -d {self.path} -i data BAD.bad.lch > temp_bad'
        system(cmd)
        Path('temp_bad').unlink()

        # Confirm that no lch file was created
        assert not Path('BAD.fix.lch').exists()

        # Compare text files (fix.txt)
        outfname = 'BAD.fix.txt'
        assert Path(outfname).exists()
        assertTextFilesEqual(self,  outfname, str(self.test_path / outfname))
        Path(outfname).unlink()

        # Compare text files (fix.timetears.txt)
        outfname = 'BAD.fix.timetears.txt'
        assert Path(outfname).exists()
        assertTextFilesEqual(self,  outfname, str(self.test_path / outfname))
        Path(outfname).unlink()

        # Compare process-steps files
        outfname = 'process-steps.json'
        assert Path(outfname).exists()
        new_outfname = 'BAD.' + outfname
        Path(outfname).rename(new_outfname)
        assertProcessStepsFilesEqual(self,  new_outfname,
                                     str(self.test_path / new_outfname))
        Path(new_outfname).unlink()


def suite():
    return unittest.makeSuite(TestLCHEAPOMethods, 'test')


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
