#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make a directory containing lcheapo examples
import argparse
import shutil
import os
import inspect


def main():
    """
    Copy _examples file to a local directory
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-d", "--destdir", default='EXAMPLES_LCHEAPO_OBSPY',
                        help="destination directory",)
    args = parser.parse_args()

    self_path = os.path.dirname(os.path.abspath(inspect.getfile(
        inspect.currentframe())))
    examples_dir = os.path.join(self_path, '_examples')

    if os.path.exists(args.destdir):
        print(f'destination directory "{args.destdir}" already exists')
    else:
        try:
            shutil.copytree(examples_dir, args.destdir)
        except shutil.Error as e:
            print(f'Directory not copied. Error: {e}')
        except OSError as e:
            print(f'Directory not copied. Error: {e}')


# ---------------------------------------------------------------------------
# Run 'main' if the script is not imported as a module
# ---------------------------------------------------------------------------
# if __name__ == '__main__':
#     main()
