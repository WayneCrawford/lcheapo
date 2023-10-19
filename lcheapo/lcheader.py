#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create/modify an LCHEAPO data file header
"""
import sys
import copy
# import os
import math as m
import argparse
from datetime import datetime, timedelta
from pathlib import Path

from lcheapo_utils import (LCDiskHeader, LCDirEntry)
from version import __version__

from sdpchain.process_steps import ProcessStep

# ------------------------------------
# Global Variable Declarations
# ------------------------------------
PROGRAM_NAME = "lcheader"
bytes_per_block = 512
dirEntries_per_dirBlock = 16
blocks_per_dirEntry = 14336
samples_per_block = 166
accepted_sample_rates = [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000]
accepted_num_channels = [1, 2, 3, 4]


def main():
    """main function"""
    opts = __getOptions()
    
    params = dict(wake_time=datetime(2017, 1, 1, 5, 0, 0),
                  end_time=datetime(2018, 1, 1, 5, 0, 0),
                  output_filename='generic.header.lch')
    if opts.input_file:
        h = __read_header(Path(opts.in_dir) / opts.input_file)
    else:
        h = __generic_header()
    if opts.description:
        h.description = opts.description
    if opts.sample_rate:
        h.realSampleRate = opts.sample_rate
        h.sampleRate = m.floor(opts.sample_rate)
    if opts.num_channels:
        h.numberOfChannels = opts.num_channels
    if opts.wake_time:
        params['wake_time'] = __get_datetime(None, opts.wake_time)
    if opts.end_time:
        params['end_time'] = __get_datetime(None, opts.end_time)
    if opts.output_file:
        params['output_filename'] = opts.output_file
    h, params = _modify_parameters(h, params, opts)
    if opts.dry_run:
        sys.exit(2)
    with open(Path(opts.out_dir) / params['output_filename'], 'wb') as fp:
        # Pre-blank file
        if opts.noDirectory:
            fp.write(b'\x00' * bytes_per_block * h.dirStart)
        else:
            fp.write(b'\x00' * bytes_per_block * h.dataStart)

        # Write header
        h.seekHeaderPosition(fp)
        h.writeHeader(fp)
        if opts.noDirectory:
            sys.exit(0)

        # Write directory
        d = __prep_dirEntry(h.sampleRate)
        dt = params['wake_time']
        dirCount = 0
        samples_per_dirEntry = samples_per_block * blocks_per_dirEntry / \
            h.numberOfChannels
        dir_timeoffset = timedelta(seconds=samples_per_dirEntry / h.sampleRate)
        blocknum = h.dataStart
        d.seekBlock(fp, h.dirStart)
        while dt < params['end_time']:
            d.blockNumber = blocknum
            d.changeTime(dt)
            d.writeDirEntry(fp)
            dt += dir_timeoffset
            dirCount += 1
            blocknum += blocks_per_dirEntry
        h.dirCount = dirCount
        h.dirBlock = h.dirStart + int(dirCount/dirEntries_per_dirBlock)
        h.seekHeaderPosition(fp)
        h.writeHeader(fp)
        
    global process_step
    process_step.parameters['wake_time'] = params['wake_time'].isoformat()
    process_step.parameters['end_time'] = params['end_time'].isoformat()
    process_step.output_file = params['output_filename']
    process_step.exit_status = 0
    process_step.write(opts.in_dir, opts.out_dir) 
    sys.exit(0)


def __getOptions():
    """
    Parse user passed options and parameters
    """
    # usageStr = "%prog [-h] [-V]"
    parser = argparse.ArgumentParser(
        description="Create/modify an LCHEAPO data file header",
        epilog="Interactive unless you specify --description, -s, -c, -w, -e "
               "and --output_file")
    parser.add_argument("-V", "--version", default=False, action="store_true",
                        help="Display Program Version")
    parser.add_argument("-n", "--noDirectory", default=False,
                        action="store_true", help="don't create a directory")
    parser.add_argument("--dry_run", default=False, action="store_true",
                        help="don't save to disk")
    parser.add_argument("--no_questions", default=False, action="store_true",
                        help="make a generic header, no questions", )
    parser.add_argument("--input_file",
                        help="input header file to modify")
    parser.add_argument("--description",
                        help="Header Description field (e.g. "
                             "Experiment_OBSType_SN_Station)")
    parser.add_argument("-s", "--sample_rate", type=float, metavar="SAMP_RATE",
                        choices=accepted_sample_rates,
                        help=f"Sample Rate. Allowed = {accepted_sample_rates}")
    parser.add_argument("-c", "--num_channels", type=int, metavar="NCHANS",
                        choices=accepted_num_channels,
                        help=f"Number of channels. Allowed = {accepted_num_channels}")
    parser.add_argument("-w", "--wake_time",  metavar="TIME",
                        help="Start of recorded data (ISO0601 format)")
    parser.add_argument("-e", "--end_time",  metavar="TIME",
                        help="End of recorded data (ISO0601 format)")
    parser.add_argument("--output_file", help="Output filename")
    parser.add_argument("-d", "--directory", dest="base_dir",
                        default='.', help="Base directory for files")
    parser.add_argument("-i", "--input", dest="in_dir", default='.',
                        help="path to input files (abs, or rel to base)")
    parser.add_argument("-o", "--output", dest="out_dir", default='.',
                        help="path for output files (abs, or rel to base)")
    args = parser.parse_args()
    global process_step
    process_step = ProcessStep('lcheader',
                               " ".join(sys.argv),
                               app_description='Create LCHEAPO header and '
                                               'directory',
                               app_version=__version__,
                               parameters=args)

    args.input_files = [args.input_file]
    args.in_dir, args.out_dir, _ = ProcessStep.setup_paths(args, expand_wildcards=False)
    args = parser.parse_args()

    # Get the filename (the arguments)
    if args.version:
        print(f"{PROGRAM_NAME} - Version: {__version__}")
        sys.exit(0)
    return args


def _modify_parameters(h, params, opts):
    """Imitate LCHEAPO parameter menu, return values"""
    filename_prefix = params['output_filename'].split('.')[0]
    while not __validate_params(h, params, opts):
        h.description = __get_string("Description (Cruise_InstModel_SN_Site)",
                                     h.description)
        h.realSampleRate = __get_float("Sample Rate", h.realSampleRate,
                                       accepted_sample_rates)
        h.sampleRate = m.floor(h.realSampleRate)
        h.numberOfChannels = __get_int("Number of Channels",
                                       h.numberOfChannels,
                                       accepted_num_channels)

        params['wake_time'] = __get_datetime("Wake Time", params['wake_time'])
        if params['end_time'] < params['wake_time']:
            params['end_time'] = params['wake_time'] + timedelta(days=365)
        params['end_time'] = __get_datetime("End Time", params['end_time'])
        filename_prefix = __get_string("Output Filename Prefix",
                                       filename_prefix)
        params['output_filename'] = filename_prefix + '.header.lch'

    datalen = params['end_time'] - params['wake_time']
    datalen_seconds = datalen.days * 86400 + datalen.seconds + \
        datalen.microseconds / 1.e6
    datalen_blocks = int(datalen_seconds * h.sampleRate / samples_per_block) *\
        h.numberOfChannels
    h.writeBlock = h.dataStart + datalen_blocks

    params['sample_rate'] = h.realSampleRate
    params['number_of_channels'] = h.numberOfChannels
    params['description'] = h.description

    return h, params


def __validate_params(h, params, opts):
    """Validate header parameters"""
    if opts.no_questions:
        return True

    print('**** PARAMETERS ****')
    print(f'         Description: {h.description}')
    print(f'         Sample Rate: {h.realSampleRate:g}')
    print(f'  Number of Channels: {h.numberOfChannels}')
    print(f'           Wake Time: {params["wake_time"].isoformat()}')
    print(f'            End Time: {params["end_time"].isoformat()}')
    print(f'     Output Filename: {params["output_filename"]}')

    if opts.description and opts.sample_rate and opts.num_channels \
            and opts.wake_time and opts.end_time and opts.output_file:
        return True

    resp = input('Is this acceptable? [y/N]: ')
    if not resp:
        return False
    if resp[0].lower() == 'y':
        return True
    return False


def __read_header(filename):
    """Read in header from an LCHEAPO file"""
    h = LCDiskHeader()
    with open(filename, 'r') as fp:
        h.seekHeaderPosition(fp)
        h.readHeader(fp)
    return h


def __generic_header():
    """Create a generic lcheapo header"""

    default_data_startblock = 3586
    default_dir_startblock = 8
    default_data_type = 2
    default_data_type_string = "Uncompressed (24-Bit)"

    h = LCDiskHeader()

    # UNUSED OR STANDARD VALUES
    h.dataType = default_data_type
    h.diskSize = 0    # GB
    h.ramSize = 8     # MB
    h.softwareVersion = '9.08a-OLD'
    h.dirStart = default_dir_startblock
    h.dataStart = default_data_startblock
    # h.dirSize=(h.dataStart-h.dirStart-1)*dirEntries_per_dirBlock
    # Modified to work with lc2ms v1
    h.dirSize = (h.dataStart - h.dirStart) * dirEntries_per_dirBlock - 1
    (h.slowStart, h.slowSize, h.slowBlock, h.slowByte) = (0, 0, 0, 0)
    (h.logStart, h.logSize, h.logBlock, h.logByte) = (0, 0, 0, 0)
    (h.slowDataRate, h.slowStartChannel, h.slowNumberOfChannels) = (0, 0, 0)
    (h.readBlock, h.startChannel, h.diskNumber) = (0, 0, 0)
    (h.numberOfWindows, h.readByte, h.writeByte) = (0, 0, 0)

    # These should be modified after writing directory
    h.dirBlock, h.dirCount = (0, 0)

    # USER-SPECIFIED VALUES
    h.description = 'generic lcheapo header'
    h.sampleRate = 125
    h.numberOfChannels = 4
    h.writeBlock = h.dataStart

    # Additions which cannot be written to file
    h.realSampleRate = h.getRealSampleRate(h.sampleRate)
    h.dataTypeString = default_data_type_string
    return h


def __prep_dirEntry(sample_rate):
    """Prepare lcheapo directory entry object"""
    d = LCDirEntry()
    d.recordLength = 0  # Unused
    d.sampleRate = sample_rate
    d.numBlocks = blocks_per_dirEntry
    d.flag = 0x49
    d.muxChannel = 0
    d.U1 = 0            # Unused
    return d


def __get_string(question, default):
    """Read a string from the command line"""
    resp = input("{} [{}]: ".format(question, default))
    if not resp:
        return default
    return resp


def __get_datetime(question, default):
    """Read a datetime from the command line"""
    if question is not None:
        resp = input("{} [{}]: ".format(question, default.isoformat()))
        if not resp:
            return default
    else:
        resp = default
    try:
        resp = datetime.strptime(resp, '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        try:
            resp = datetime.strptime(resp, '%Y-%m-%dT%H:%M:%S.%f')
        except ValueError:
            print('Invalid input: {}'.format(resp))
            if question is not None:
                resp = __get_datetime(question, default)
            else:
                sys.exit(2)
    return resp


def __get_int(question, default, possibles=False):
    """Read an int from the command line"""
    resp = input("{} [{:d}]: ".format(question, default))
    if not resp:
        return default
    else:
        try:
            resp = int(resp)
        except ValueError:
            print('Invalid input: {}'.format(resp))
            resp = __get_int(question, default, possibles)
        if isinstance(possibles, list):
            if resp not in possibles:
                print('Input must be one of: {}'.format(str(possibles)))
                resp = __get_int(question, default, possibles)
    return resp


def __get_float(question, default, possibles=False):
    """Read a float from the command line"""
    resp = input("{} [{:g}]: ".format(question, default))
    if not resp:
        return default
    else:
        try:
            resp = float(resp)
        except ValueError:
            if isinstance(possibles, list):
                print('Input must be one of: {}'.format(str(possibles)))
            else:
                print('Invalid input: {}'.format(resp))
            resp = __get_float(question, default, possibles)
        if isinstance(possibles, list):
            if resp not in possibles:
                print('Input must be one of: {}'.format(str(possibles)))
                resp = __get_float(question, default, possibles)
    return resp


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
