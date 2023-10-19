#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cut an LCHEAPO file into pieces

Used to remove bad/empty blocks, blocks start with 0 and are 512-bytes
"""
import argparse
import copy
# import os
from datetime import datetime as dt
import sys
from math import floor
from pathlib import Path

from sdpchain import ProcessStep
from version import __version__

BLOCK_SIZE = 512
MAX_BLOCK_READ = 2048   # max number of blocks to read at once


def main():
    return_code = 0
    exec_messages = []

    # GET ARGUMENTS
    args = getOptions()

    # Verify output filename
    if not args.output_file:
        # Create output filename
        base = Path(args.input_files[0]).stem
        ext = Path(args.input_files[0]).suffix
        args.output_file = f'{base}_{args.start:d}_{args.end:d}{ext}'
    out_path = Path(args.out_dir) / args.output_file
    if out_path.exists():
        print(f'output file {str(out_path)} exists already, quitting...')
        sys.exit(2)

    with open(Path(args.in_dir) / args.input_files[0], 'rb') as fp:
        # Set/validate last block to read
        fp.seek(0, 2)   # End of file
        last_file_block = floor(fp.tell()/BLOCK_SIZE)-1
        if args.end:
            if args.end > last_file_block:
                args.end = last_file_block
        else:
            args.end = last_file_block
        # Quit if start block is after EOF and/or end block
        if args.start > last_file_block:
            return_code = 2
            msg = 'Error: --start block [{:d}] is beyond EOF [{:d}]'.format(
                args.start, last_file_block)
            print(msg)
            exec_messages.append(msg)
        elif args.start > args.end:
            return_code = 3
            msg = 'Error: --start block [{:d}] is beyond --end [{:d}]'.format(
                args.start, args.end)
            print(msg)
            exec_messages.append(msg)
        else:
            msg = 'Writing blocks {:d}-{:d} to {}'.format(
                args.start, args.end, args.output_file)
            if args.quiet is False:
                print(msg)
            exec_messages.append(msg)
            with open(out_path, 'wb') as of:
                start_block = args.start
                fp.seek(start_block * BLOCK_SIZE, 0)
                while start_block <= args.end:
                    if (args.end-start_block+1) < MAX_BLOCK_READ:  # NEAR EOF
                        of.write(fp.read((args.end
                                          - start_block
                                          + 1) * BLOCK_SIZE))
                        break
                    else:
                        of.write(fp.read(MAX_BLOCK_READ * BLOCK_SIZE))
                        start_block += MAX_BLOCK_READ
    # Save/append process information to process_steps file
    global process_step
    process_step.messages = exec_messages
    process_step.out_file = args.output_file
    process_step.exit_code = return_code
    process_step.write(args.in_dir, args.out_dir, verbose=True)


def getOptions():
    """
    Parse user passed options and parameters.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_files", nargs=1, help="Input filename")
    parser.add_argument("--of", dest="output_file", default="",
                        help="""
                        Output filename.  If not provided, writes to
                        {root}_{start}_{end}.{ext}, where {ext} is the last
                        pathname component of {in_file_name} and {root} is
                        the rest""")
    parser.add_argument("--start", type=int, default=0,
                        help="start block to write out (0 if not specified)")
    parser.add_argument("--end", type=int, default=0,
                        help=""" last block to write out (end of file if not
                        specified)""")
    parser.add_argument("-d", "--directory", dest="base_dir",
                        default='.', help="Base directory for files")
    parser.add_argument("-i", "--input", dest="in_dir", default='.',
                        help="path to input files (abs, or rel to base)")
    parser.add_argument("-o", "--output", dest="out_dir", default='.',
                        help="path for output files (abs, or rel to base)")
    parser.add_argument("--quiet", action='store_true',
                        help="Don't print to stdout for normal operation")
    args = parser.parse_args()
    global process_step
    process_step = ProcessStep('lccut',
                               " ".join(sys.argv),
                               app_description=__doc__,
                               app_version=__version__,
                               parameters=args)
    args.in_dir, args.out_dir, _ = ProcessStep.setup_paths(args)
    return args


if __name__ == '__main__':
    main()
