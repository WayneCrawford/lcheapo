#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Read LCHEAPO data into an obspy stream
"""
import argparse
import warnings
# import os
import sys
# import datetime
import inspect
from pathlib import Path

from sdpchainpy import ProcessStep

# from .sdpchain import ProcessStep
from obspy.core import UTCDateTime
from obspy.core.inventory import Inventory, Network, read_inventory
from progress.bar import IncrementalBar

from .instrument_metadata import chan_maps, load_station
from .lcread import read as lcread, get_data_timelimits
from .version import __version__


def main():
    """
    Convert fixed LCHEAPO data to SeisComp Data Structure

    SIMPLE drift and leapsecond correction:
        - offset is constant within each daily file
        - offset information is not written in header
        - data quality field is not modified
        - leapsecond flag is not raised (causes apparent 1-s gap/overlap).
    Doesn't combine one day's SDS files made from two different LCHEAPO files
      (last one overwrites first)
    Writes to a directory named SDS/ in the output directory.
    """
    args, process_step = _get_args()

    # ADJUST INPUT PARAMETERS
    if args.sync_start_times is not None:
        args.sync_start_times = [UTCDateTime(x) for x in args.sync_start_times]
    if args.sync_end_times is not None:
        args.sync_end_times = [UTCDateTime(x) for x in args.sync_end_times]
    ls_times, ls_types = _adjust_leapseconds(args.leapsecond_times,
                                             args.leapsecond_types)

    # Set up clock drift calculation
    if args.sync_start_times and args.sync_end_times:
        ref_start = args.sync_start_times[0]
        if len(args.sync_start_times) > 1:
            inst_start = args.sync_start_times[1]
        else:
            inst_start = ref_start
        ref_end, inst_end = args.sync_end_times
        if inst_start == 0:
            inst_start = ref_start
        inst_start_offset = inst_start - ref_start
        inst_drift = ((inst_end - ref_end) - inst_start_offset)\
            / (ref_end - inst_start)
        print('instrument start offset = {:g}s, drift rate = {:.4g}'
              .format(inst_start_offset, inst_drift))
        quality_flag = 'Q'
    else:
        inst_start_offset = 0
        inst_drift = 0
        warnings.warn('Could not calculate clock drift, setting quality flag to "D')
        quality_flag = 'D'

    first_time = True
    for infile in args.input_files:
        lc_start, lc_end = get_data_timelimits(Path(args.in_dir) / infile)

        # Set up clock drift calculation
        if not (args.sync_start_times and args.sync_end_times):
            ref_start, inst_start = lc_start, lc_start

        if first_time is True:
            first_start = lc_start
            first_time = False

        lc_start_day = lc_start.replace(hour=0, minute=0, second=0,
                                        microsecond=0)
        lc_end_day = lc_end.replace(hour=0, minute=0, second=0, microsecond=0)
        stime = lc_start_day
        bar = IncrementalBar(f'Processing {infile}',
                             max=(lc_end_day-lc_start_day)/86400 + 1)
        while stime <= lc_end_day:
            inst_offset = inst_start_offset + inst_drift * (stime - ref_start)
            sampling_rate = _write_daily(inst_offset, stime, infile,
                                       args, ls_times, ls_types, quality_flag)
            bar.next()
            stime += 86400
        bar.finish()

    if args.xml is True:
        _write_stationxml(sampling_rate, first_start, lc_end, args)

    return_code = 0
    process_step.exit_code = return_code
    process_step.write(args.in_dir, args.out_dir)
    sys.exit(return_code)


def _write_stationxml(sampling_rate, start_date, end_date, args):
    """
    Write or overwrite StationXML file 'SDS.station.xml'

    Args:
        sampling_rate (float): data sampling rate (sps)
        start_date(UTCDateTime)
        end_date(UTCDateTime)
        args (NameSpace): Command-line arguments
    """
    inv_file = Path(args.out_dir) / 'SDS.station.xml'
    station = load_station(args.obs_type, sampling_rate, starttime=start_date)
    station.code = args.station
    for channel in station:
        channel.start_date = start_date
        channel.end_date = end_date
    station.start_date = start_date
    station.end_date = end_date
    if inv_file.exists():
        inv = read_inventory(inv_file, format='STATIONXML')
        assert len(inv.select(network=args.network)) == 1
        net = inv.networks[0]
        if net.start_date > start_date:
            net.start_date = start_date
        if net.end_date < end_date:
            net.end_date = end_date
        net.stations.append(station)
    else:
        inv = Inventory(source='lc2SDS_py',
                        networks=[Network(args.network,
                                          stations=[station],
                                          start_date=start_date,
                                          end_date=end_date)])
    inv.write(str(inv_file), format='STATIONXML')

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


def _get_args():
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
    parser.add_argument("-s", "--sync_start_times", nargs='+',
                        metavar=("REF_START", "INST_START"),
                        help="Start datetimes for the reference (usually GPS) "
                             "and instrument.  If only one value is provided, "
                             "it will be used for both")
    parser.add_argument("-e", "--sync_end_times", nargs=2,
                        metavar=("REF_END", "INST_END"),
                        help="End datetimes for the reference and instrument")
    parser.add_argument("--leapsecond_times", nargs='+',
                        help="leapsecond times")
    parser.add_argument("--leapsecond_types", default='+',
                        help="'+' for extra second, '-' for removed second. "
                             "If there is one character it is applied to all "
                             "leapseconds, if there is more than one the "
                             "length of the string must match "
                             "the number of leapsecond_times")
    parser.add_argument("-d", dest="base_dir", metavar="BASE_DIR",
                        default='.', help="base directory for files")
    parser.add_argument("-i", dest="in_dir", metavar="IN_DIR", default='.',
                        help="input file directory (absolute, " +
                             "or relative to base_dir)")
    parser.add_argument("-o", dest="out_dir", metavar="OUT_DIR", default='.',
                        help="output file directory (absolute, " +
                             "or relative to base_dir)")
    parser.add_argument("-x", "--xml", action='store_true',
                        help="Create/append StationXML file SDS.station.xml "
                             "with station characteristics")
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="verbose output")
    parser.add_argument("--version", action='store_true',
                        help="Print version number and quit")
    args = parser.parse_args()
    parameters = vars(args).copy()
    if args.version is True:
        print(f"Version {__version__}")
        sys.exit(0)

    # SETUP FOR PROCESS-STEPS
    process_step = ProcessStep('lc2SDS',
                               " ".join(sys.argv),
                               app_description=__doc__,
                               app_version=__version__,
                               parameters=parameters)
    args.in_dir, args.out_dir, args.input_files = ProcessStep.setup_paths(args)
    # Expand captured wildcards
    # args.input_files = [x.name for f in args.input_files
    #                     for x in Path(args.in_dir).glob(f)]

    return args, process_step


def _write_daily(inst_offset, stime, infile, args, ls_times, ls_types,
                 qualityflag):
    assert qualityflag in ['D', 'Q'], f'{qualityflag=} is not "D" or "Q"'
    starttime = stime + inst_offset
    endtime = starttime + 86400
    if args.verbose:
        print('{}, inst_offset = {:.3f}s: reading {}-{}'.format(
            stime.strftime('%Y-%m-%d'), inst_offset,
            starttime.isoformat(), endtime.isoformat()))
    stream = lcread(Path(args.in_dir) / infile,
                    starttime=starttime,
                    endtime=endtime,
                    network=args.network,
                    station=args.station,
                    obs_type=args.obs_type)

    sampling_rate = None
    for tr in stream:
        s = tr.stats
        if sampling_rate is None:
            sampling_rate = s.sampling_rate
        else:
            assert s.sampling_rate == sampling_rate, "traces do not all have the same sampling rate!"
        # Correct leapsecond
        s.starttime += _leap_correct(stime, ls_times, ls_types)
        # Correct drift
        s.starttime -= inst_offset
        s.mseed = {'dataquality': qualityflag}

        # Write file
        dirname = Path(args.out_dir) / 'SDS' / str(stime.year) /\
            s.network / s.station / f'{s.channel}.D'
        fname = '{}.{}.{}.{}.D.{}.{:03d}'.format(
            s.network, s.station, s.location, s.channel,
            stime.year, stime.julday)
        dirname.mkdir(parents=True, exist_ok=True)
        tr.write(str(dirname / fname), format='MSEED',
                 encoding='STEIM1', reclen=4096)
    return sampling_rate


def _adjust_leapseconds(ls_times, ls_types):
    """
    Adjust leapsecond arguments

    Converts times to UTCDateTime and makes sure there is one type
    for each time
    :param ls_times: list of strings
    :param ls_types: str
    :returns: ls_times, ls_types
    """
    if ls_times is None:
        return ls_times, ls_types
    # Quick and stupid way to avoid second=60 problem
    new_times = []
    for t in ls_times:
        if t[-2:] == '60':
            t = t[:-2] + '59'
        new_times.append(UTCDateTime(t))
    if not len(new_times) == len(ls_types):
        if len(ls_types) == 1:
            ls_types = ls_types * len(new_times)
        else:
            raise IndexError(f"len(ls_times) ({len(new_times)}) "
                             "incompatible with "
                             f"len(ls_types) {len(ls_types)}")
    for tp in ls_types:
        if tp not in '+-':
            raise ValueError(f"'{tp}' is not a valid leapsecond type")
    return new_times, ls_types


def _leap_correct(starttime, ls_times, ls_types):
    """
    Return leap-second correction for a given time
    :param starttime: time at start of current data segment
    :type starttime: UTCDateTime
    :param ls_times: list of leap second times.
    :param ls_types: str of leap second types ('+' or '-').  If len(ls_times)
        is not 0, ls_types and ls_times must have same length
    :returns: seconds to add to current OBS-recorded time
    """
    if ls_times is None:
        return 0
    correct = 0
    for ls_time, ls_type in zip(ls_times, ls_types):
        if starttime > ls_time - 1:  # avoid overlap with leap seconds
            if ls_type == '+':
                correct -= 1  # Everything after an added second is one earlier
            elif ls_type == '-':
                correct += 1
            else:
                raise ValueError(f"'{ls_type}' is not a valid leapsecond type")
    return correct


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
# if __name__ == '__main__':
#     main()
