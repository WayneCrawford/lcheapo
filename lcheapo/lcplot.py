#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read LCHEAPO data into an obspy stream
"""
import argparse
import re

from obspy.core import UTCDateTime, Stream

from chan_maps import chan_maps
from lcread import read, get_data_timelimits


def main():
    """
    Command-line plotting interface
    """

    obs_types = [s for s in chan_maps]
    epilog = "--sfilt returns the first parenthetised subgroup, using \n"
    epilog += "  python's re.search().  Some useful codes are: \n"
    epilog += "   '.': matches any character\n"
    epilog += "   '+': matches 1 or more repetitions of the preceding RE\n"
    epilog += "   '?': matches 0 or 1 repetitions of the preceding RE\n"
    epilog += "  '+?': like +, but non-greedy (don't match as many as possible)\n"
    epilog += "   '\\': escapes special characters, like '*', '-' and '/')\n"
    epilog += "  '()': delimit the subgroup to return\n\n"
    epilog += " Some examples are: \n"
    epilog += "    FILENAME                 |   PATTERN      |     RESULT\n"
    epilog += "    =========================+================+=============\n"
    epilog += "    haha-MOVA-OBS1-blah.lch | '\-(.+)\-'     | MOVA-OBS1 \n"
    epilog += "    haha-MOVA-OBS1-blah.lch | '\(-.+)\-.+\-' | MOVA \n"
    epilog += "    haha-MOVA-OBS1-blah.lch | '\-.+\-(.+)\-' | OBS1 \n"
    epilog += "    MOVA/haha.raw.lch       | '([^\/]+)'     | MOVA \n"

    parser = argparse.ArgumentParser(
        description=__doc__, epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("infiles", nargs="+", help="Input filename(s)")
    parser.add_argument("-s", "--start", dest="starttime", metavar="TIME",
                        default=0,
                        help="start time (ISO8601, or seconds after last file "
                             "start) (default: %(default)s)")
    parser.add_argument("-e", "--end",
                        dest="endtime", metavar="TIME", default=3600.,
                        help="end time (ISO8601, or seconds from start time) "
                        "(default: %(default)s)")
    parser.add_argument("-t", "--type", choices=obs_types,
                        dest="obs_type", metavar='TYPE', default='SPOBS2',
                        help="obs type.  Allowed choices are " +
                             ", ".join(obs_types) +
                             " (default: %(default)s)")
    parser.add_argument("--net", dest="network", default='NN',
                        help="network code (default: %(default)s)")
    parser.add_argument("--chan", dest="channel", default='*',
                        help="Plot only the given SEED channel/s (default: "
                             "%(default)s)")
    parser.add_argument("--equal_scale", action="store_true",
                        help="Force all traces equal y scale")
    parser.add_argument('-v', "--verbose",
                        dest="verbose", action="store_true",
                        help="Print information about the first and last "
                             "read blocks")
    my_group = parser.add_mutually_exclusive_group(required=False)
    my_group.add_argument("--sta", dest="station", default='STA',
                          help="station code.  A 2-digit counter will be "
                               "appended if more than one file is read. "
                               "(default: %(default)s)")
    my_group.add_argument("--sfilt", dest="station_filt",
                          help="regex filter to find station name in filename "
                               "(see examples below)")
    args = parser.parse_args()

    # Set/normalize start and end times
    endtime = _normalize_time_arg(args.endtime)
    if endtime == 0:
        endtime = 3600.
    if not args.starttime:  # set starttime to latest-starting file
        args.starttime = UTCDateTime(0)
        for infile in args.infiles:
            s, e = get_data_timelimits(infile)
            if s > args.starttime:
                args.starttime = s
    # Read file(s)
    station_code = None
    if args.station:
        if len(args.infiles) == 1:
            station_code = args.station
    stream = Stream()
    for (infile, i) in zip(args.infiles, range(len(args.infiles))):
        if args.station_filt:
            # print(re.search(args.station_filt, infile))
            try:
                station_code = re.search(args.station_filt, infile).group(1)
            except Exception:
                print('no station code found using re.search("{}", "{}"'.
                      format(args.station_filt, infile))
                station_code = None
        if station_code is None:
            station_code = f'STA{i:02d}'
        s = read(infile,
                 _normalize_time_arg(args.starttime),
                 _normalize_time_arg(args.endtime),
                 network=args.network,
                 station=station_code,
                 obs_type=args.obs_type,
                 verbose=args.verbose)
        if s is not None:
            s = s.select(channel=args.channel)
            stream += s
            station_code = None
    if len(stream) > 0:
        stream.plot(size=(800, 600), equal_scale=args.equal_scale,
                    method='full')
    else:
        print('Nothing read, nothing plotted!')


def _normalize_time_arg(a):
    """
    Convert time from string to float if it is numeric
    """
    if isinstance(a, UTCDateTime):
        return a
    try:
        temp = float(a)
    except ValueError:
        return a
    else:
        return temp

# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
