#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Return basic information about LCHEAPO files

By default, returns number of channels, samp_rate and start
and end of each file
"""
from sdpchain import ProcessStep
from lcheapo_utils import (LCDataBlock, LCDiskHeader)
import argparse
import os
from datetime import timedelta

from version import __version__


def main():
    global warnings

    # GET ARGUMENTS
    args = getOptions()
    in_filename_path, out_filename_path, _ = ProcessStep.setup_paths(args)

    for filename in args.input_files:
        with open(os.path.join(in_filename_path, filename),
                  'rb') as fp:
            print('-'*60)
            print(filename)
            _print_Info(fp)


def getOptions():
    """
    Parse user passed options and parameters.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_files", metavar="inFileName", nargs='+',
                        help="Input filename(s)")
    parser.add_argument("-d", dest="base_dir", metavar="BASE_DIR",
                        default='.', help="base directory for files")
    parser.add_argument("-i", dest="in_dir", metavar="IN_DIR",
                        default='.', help="input file directory (absolute, " +
                                          "or relative to base_dir)")
    parser.add_argument("-o", dest="out_dir", metavar="IN_DIR",
                        default='.', help="unused")
    parser.add_argument("--version", action='version',
                        version='%(prog)s {:s}'.format(__version__))
    args = parser.parse_args()
    return args


def _get_times(fp, block_num, samp_rate):
    """
    Get start and end time of the given block
    """
    lcData = LCDataBlock()
    lcData.seekBlock(fp, block_num)
    lcData.readBlock(fp)
    first_time = lcData.getDateTime()
    last_time = first_time + timedelta(seconds=lcData.numberOfSamples
                                               / samp_rate)
    return first_time, last_time


def _print_Info(fp):
    """
    Print out file information
    """
    lcHeader = LCDiskHeader()
    lcHeader.seekHeaderPosition(fp)
    status = lcHeader.readHeader(fp)
    if status == 0:
        print("Assuming data blocks start at block 0, wish me luck...")
        first_data_block = 0
        n_channels, sample_rate = _estimate_parms(fp, first_data_block)
    else:
        sample_rate = lcHeader.realSampleRate
        n_channels = lcHeader.numberOfChannels
        first_data_block = lcHeader.dataStart
    
    fp.seek(0, 2)                # Seek end of file
    last_data_block = int(fp.tell() / 512) - 1

    start_time, temp = _get_times(fp, first_data_block, sample_rate)
    temp, end_time = _get_times(fp, last_data_block, sample_rate)

    print('n_channels  = {:d}'.format(n_channels))
    print('sample rate = {:g}'.format(sample_rate))
    print('start time  = {}'.format(start_time))
    print('end time    = {}'.format(end_time))


def _estimate_parms(fp, first_data_block, imax=10):
    lcData = LCDataBlock()
    base_sample_rate = 62.5
    n_samples = 166
    n_channels = 1
    for i in range(imax):
        lcData.seekBlock(fp, i)
        lcData.readBlock(fp)
        # lcData.prettyPrintHeader()
        if lcData.muxChannel + 1 > n_channels:
            n_channels = lcData.muxChannel + 1
    # print(f'{n_channels=}')
    if n_channels >=imax:
        raise ValueError('File indicates more channels {:d} than tested {:d}'
                         .format(n_channels, imax))
    block_timedelta = (_get_times(fp, first_data_block + n_channels, 1)[0]
                       - _get_times(fp, first_data_block, 1)[0])
    # print(f'{block_timedelta=}')
    sample_rate = n_samples / ((block_timedelta/timedelta(milliseconds=1))/1000)
    rate_multiplier = sample_rate/base_sample_rate
    if not rate_multiplier == int(rate_multiplier):
        raise ValueError('Sample rate ({:f}) is not a multiple of {:f}'
                        .format (sample_rate, base_sample_rate))
    return n_channels, sample_rate

if __name__ == '__main__':
    main()
