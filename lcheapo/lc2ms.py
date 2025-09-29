#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create miniSEED file(s) from LCHEAPO file(s)
"""
import argparse
# import os
import sys
# import datetime
import inspect
from pathlib import Path

from sdpchainpy import ProcessStep

# from .sdpchain import ProcessStep
from instrument_metadata import chan_maps
from lcread import read as lcread
from version import __version__


def _verify_station_code(s):
    if not s.isalnum():
        raise argparse.ArgumentTypeError(f'Station code "{s}" has non-alphanumeric values')
    if len(s) > 5:
        raise argparse.ArgumentTypeError(f'Station code "{s}" is > 5 characters long')
    return s

def _verify_network_code(s):
    if not s.isalnum():
        raise argparse.ArgumentTypeError(f'Network code "{s}" has non-alphanumeric values')
    if len(s) > 2:
        raise argparse.ArgumentTypeError(f'Network code "{s}" is > 2 characters long')
    return s


def main():
    """
    Convert LCHEAPO data to basic miniSEED files for Epos-France SMM A-node
    One file per trace, filenames are {seed.id}.{YYYYmmdd}T{HHMM}.mseed
    No drift or leapsecond correction:
    """
    print(main.__doc__)
    parser = argparse.ArgumentParser(
        description=inspect.cleandoc(main.__doc__),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_files", nargs='+',
                        help="Input filename(s).  If there are captured "
                             "wildcards (put in '' so that they aren't "
                             "interpreted by the shell), will expand them "
                             "in the input directory")
    parser.add_argument("-t", "--obs_type", default='SPOBS2',
                        help="obs type.  Controls channel and location codes",
                        choices=[s for s in chan_maps])
    parser.add_argument("--station", default='SSSSS',
                        type=_verify_station_code,
                        help="station code for this instrument (default=SSSSS)")
    parser.add_argument("--network", default='XX',
                        type=_verify_network_code,
                        help="network code for this instrument (default=XX)")
    parser.add_argument("-d", dest="base_dir", metavar="BASE_DIR",
                        default='.', help="base directory for files")
    parser.add_argument("-i", dest="in_dir", metavar="IN_DIR", default='.',
                        help="input file directory (absolute, " +
                             "or relative to base_dir)")
    parser.add_argument("-o", dest="out_dir", metavar="OUT_DIR", default='.',
                        help="output file directory (absolute, " +
                             "or relative to base_dir)")
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="verbose output")
    parser.add_argument("--version", action='store_true',
                        help="Print version number and quit")
    args = parser.parse_args()
    parameters = vars(args).copy()
    if args.version is True:
        print(f"Version {__version__}")
        sys.exit(0)

    # ADJUST INPUT PARAMETERS
    process_step = ProcessStep('lc2ms_py',
                               " ".join(sys.argv),
                               app_description=__doc__,
                               app_version=__version__,
                               parameters=parameters)
    args.in_dir, args.out_dir, args.input_files = ProcessStep.setup_paths(args)
    # Expand captured wildcards
    # args.input_files = [x.name for f in args.infiles
    #                 for x in Path(args.in_dir).glob(f)]

    for infile in args.input_files:
        stream = lcread(Path(args.in_dir) / infile, network=args.network,
                        station=args.station, obs_type=args.obs_type,
                        starttime=0,
                        endtime=1*86400*365.25)  # For up to 1 year of data
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_files = []
        for tr in stream:
            s = tr.stats
            out_files.append('{}_{}.mseed'.format(
                tr.id, s.starttime.strftime("%Y%m%dT%H%M")))
            fname = str(out_dir / out_files[-1])
            tr.write(fname, format='MSEED', encoding='STEIM1', reclen=4096)
    return_code = 0
    process_step.output_files = out_files
    process_step.exit_code = return_code
    process_step.write(args.in_dir, args.out_dir)
    sys.exit(return_code)


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
# if __name__ == '__main__':
#     main()
