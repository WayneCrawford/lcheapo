#!/usr/bin/env python
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
from math import ceil

from sdpchainpy import ProcessStep

# from .sdpchain import ProcessStep
from .instrument_metadata import chan_maps
from .lcread import read as lcread
from .version import __version__

MAX_TRACE_LEN = 500000000  # write_mseed seems to be limited to about 2GB.


def _verify_station_code(s):
    if not s.isalnum():
        raise argparse.ArgumentTypeError(f'Station code "{s}" has non-alphanumeric values')
    if len(s) > 5:
        raise argparse.ArgumentTypeError(f'Station code "{s}" > 5 characters long')
    return s


def _verify_network_code(s):
    if not s.isalnum():
        raise argparse.ArgumentTypeError(f'Network code "{s}" has non-alphanumeric values')
    if len(s) > 2:
        raise argparse.ArgumentTypeError(f'Network code "{s}" > 2 characters long')
    return s


def main():
    """
    Convert LCHEAPO data to basic miniSEED files for Epos-France SMM A-node
    Creates one file per trace per input file, no clock correction is applied
    Output filenames are {seed_id}.{YYYYmmdd}T{HHMM}.mseed

    Writes `glue_script.sh` if you have more than
    one output file per seed_id. `glue_script.sh` requires `msmod`

    Only works for datasets less than one year
    """
    args, process_step = _get_args()

    max_read_s = 1*86400*365.25
    need_glue_script = False
    for infile in args.input_files:
        if args.quiet is not True:
            print(f'Reading from "{infile}" ...', end='', flush=True)
        stream = lcread(Path(args.in_dir) / infile, network=args.network,
                        station=args.station, obs_type=args.obs_type,
                        starttime=0,
                        endtime=max_read_s)  # For up to 1 year of data
        if args.quiet is not True:
            print('Done')
        if stream[0].stats.endtime - stream[0].stats.starttime > max_read_s:
            raise ValueError(f'Input file is longer than {max_read_s=}')
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_files = []
        for tr in stream:
            if len(tr) > MAX_TRACE_LEN:
                need_glue_script = True
                out_files.extend(_cut_and_save(tr, out_dir, args.quiet))
            else:
                out_files.append(_save_trace(tr, out_dir, args.quiet))
    return_code = 0
    process_step.output_files = out_files
    process_step.exit_code = return_code
    process_step.write(args.in_dir, args.out_dir)
    if need_glue_script is True:
        print(80*'=')
        print(f'Run glue_script.sh to glue files together')
        _write_glue_script(out_dir)  # Writes script to "glue" miniSEED files
    sys.exit(return_code)


def _get_args():
    """
    Get command-line arguments
    """
    # Create parser and add arguments
    parser = argparse.ArgumentParser(
        description=inspect.cleandoc(main.__doc__),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input_files", nargs='+',
                        help="Input filename(s).  If there are wildcards to "
                             "capture, put in '' so that they aren't "
                             "interpreted by the shell")
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
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--verbose", action='store_true',
                       help="verbose output")
    group.add_argument("-q", "--quiet", default=False, action='store_true',
                       help="no command-line output at all")
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
    return args, process_step


def _cut_and_save(tr, out_dir, quiet):
    nfiles = int(ceil(len(tr)/MAX_TRACE_LEN))
    print(f'  Trace length={len(tr)} > {MAX_TRACE_LEN=}, saving to {nfiles} files')
    start_addr = 0
    sr = tr.stats.sampling_rate
    outfiles = []
    while start_addr < len(tr):
        end_addr = start_addr + MAX_TRACE_LEN
        if end_addr > len(tr) + 1:
            end_addr = len(tr) + 1
        tr_cut = tr.copy()
        tr_cut.data = tr_cut.data[start_addr:end_addr]
        tr_cut.stats.starttime = tr.stats.starttime + start_addr/sr
        outfiles.append(_save_trace(tr_cut, out_dir, quiet))
        start_addr += MAX_TRACE_LEN
    return outfiles


def _save_trace(tr, out_dir, quiet):
    fname = f'{tr.id}_{tr.stats.starttime.strftime("%Y%m%dT%H%M")}.mseed'
    fpath = str(out_dir / fname)
    if quiet is not True:
        print(f'    Saving to "{fname}"', end=' ...', flush=True)
    tr.write(fpath, format='MSEED', encoding='STEIM1', reclen=4096)
    if quiet is not True:
        print(' Done')
    return fname


def _write_glue_script(out_dir):
    out_path = out_dir / 'glue_script.sh'
    if out_path.exists():
        return
    with open(str(out_path), 'w') as fid:
        fid.write('#! /bin/bash\n')
        fid.write('# Requires msmod, downloadable from https://github.com/EarthScope/msmod\n')
        fid.write("net='*'\n")
        fid.write("sta='*'\n")
        fid.write("loc='*'\n")
        fid.write("cha='*'\n")
        fid.write('# Use msmod to glue identical seed_ids together\n')
        fid.write('msmod ${net}.${sta}.${loc}.${cha}_*T*.mseed -A %n.%s.%l.%c.mseed\n\n')
        fid.write('# Remove original files (commented out by default)\n')
        fid.write('# rm *.*.*.*_*T*.mseed\n')


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
# if __name__ == '__main__':
#     main()
