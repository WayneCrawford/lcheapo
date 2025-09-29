#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dump record information from an LCHEAPO file
"""
from pathlib import Path

import sys
import argparse
import datetime as dt

from lcheapo_utils import (LCDiskHeader, LCDirEntry, LCDataBlock)


# ------------------------------------
# Global Variable Declarations
# ------------------------------------
PROGRAM_NAME = "lcdump"
VERSION = "0.2.3"
version_notes = """
    v0.2 (2015/01): WCC added format options
    v0.2.1 (2017/01): WCC added possibility to compare time with theoretical
    v0.2.2 (2017/03): WCC added directory printing
    v0.2.3 (2017/03): Added "--from_end" option
    """


def getOptions():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inFilename", help="LCHEAPO file name")
    parser.add_argument("startBlock", type=int, default=5000,
                        help="block at which to start dump")
    parser.add_argument("nBlocks", type=int, default=10,
                        help="number of blocks to dump")
    parser.add_argument("-r", "--from_end", default=False, action="store_true",
                        help="Count startBlocks back from end of file")
    parser.add_argument("-v", "--version", default=False, action="store_true",
                        help="Display Program Version")
    parser.add_argument("-p", "--printHeader", default=False,
                        action="store_true",  help="Print disk header")
    parser.add_argument("-d", "--printDirectory", default=False,
                        action="store_true",  help="Print disk directory")
    parser.add_argument("-f", "--format", type=int, default=0,
                        choices=[0, 1, 2, 3],
                        help="Output format: 0=pretty [default], 1=decimal,\
                        2=hex, 3=time_verify")
    args = parser.parse_args()

    # Get the filename (the arguments)
    if args.version:
        print("{} - Version: {}".format(PROGRAM_NAME, VERSION))
        sys.exit(0)

    return args


def main():

    args = getOptions()

    if args.from_end is True:
        args.startBlock = int(Path(args.inFilename).stat().st_size/512)-args.startBlock

    fp = open(args.inFilename, 'rb')
    if args.printHeader or (args.format == 3) or args.printDirectory:
        lcHeader = LCDiskHeader()
        lcHeader.readHeader(fp)
        if args.printHeader:
            lcHeader.printHeader()
        if args.printDirectory:
            lcDir = LCDirEntry()
            lcDir.seekBlock(fp, lcHeader.dirStart)
            iDir = 0
            print("="*80)
            print(" {:25s} {:8s} {:15s} {:10s} {:12s} {:11s} {}".format(
                "DateTime", "MuxChan", "SPS", "block#",
                "numBlocks", "recordLen", "Flag"))
            print("="*80)
            while iDir < lcHeader.dirCount:
                lcDir.readDirEntry(fp)
                print(lcDir)
                iDir = iDir + 1

    if args.format == 3:
        firstBlock = lcHeader.dataStart
        if firstBlock == 0:   # normal start block
            firstBlock = 2393
        lcStartData = LCDataBlock()
        lcStartData.seekBlock(fp, firstBlock)
        lcStartData.readBlock(fp)
        firstTime = dt.datetime(lcStartData.year+2000,
                                lcStartData.month,
                                lcStartData.day,
                                lcStartData.hour,
                                lcStartData.minute,
                                lcStartData.second,
                                lcStartData.msec*1000)
        print("First block = {:d}: Time = {} ".format(firstBlock,
              firstTime.strftime('%Y/%m/%d-%H:%M:%S.%f')[:-3]))
        sampRate = lcHeader.realSampleRate
        if sampRate == 0:
            sampRate = 62.5
            print("Sample rate not in directory header, assuming 62.5")
        print(" {:>7s}: {:^2s} | {:^23s} | {:^23s} | {:>8s} ".format(
              "BLOCK", "CH", "EXPECTED TIME", "FOUND TIME", "DELTA"))
        print("-{:->7s}:-{:-^2s}-|-{:-^23s}-|-{:-^23s}-|-{:->8s}-".format(
              "-", "-", "-", "-", "-"))

    block = args.startBlock
    lcData = LCDataBlock()
    lcData.seekBlock(fp, block)

    for i in range(0, args.nBlocks):
        lcData.readBlock(fp)
        print("{:8d}:".format(args.startBlock + i), end=' ')
        if args.format == 3:
            time = dt.datetime(lcData.year + 2000,
                               lcData.month,
                               lcData.day,
                               lcData.hour,
                               lcData.minute,
                               lcData.second,
                               lcData.msec * 1000)
            rec_offset = int((args.startBlock + i - firstBlock) / 4)
            calcTime = firstTime + dt.timedelta(
                       seconds=rec_offset*lcData.numberOfSamples/sampRate)
            print("{:2d} | {} | {} | {:8.3f}".format(
                lcData.muxChannel,
                calcTime.strftime('%Y/%m/%d-%H:%M:%S.%f')[:-3],
                time.strftime('%Y/%m/%d-%H:%M:%S.%f')[:-3],
                (time-calcTime).total_seconds())
            )
        elif args.format == 1:
            lcData.printDecimalDumpOfHeader(True)
        elif args.format == 2:
            lcData.printHexDumpOfData()
        elif args.format == 0:
            lcData.prettyPrintHeader()
        else:
            print("ERROR! Shouldn't get here!")


# Run 'main' if the script is not imported as a module
if __name__ == '__main__':
    main()
