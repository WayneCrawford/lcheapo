
### v2.4
lcfix runs 3-6x faster.

### v2.3

- ``lcfix`` Allow a ``forcedStartTime`` if ``forceTimes`` is set
- ``lcdump`` added a "dump data" option
- ``lcheader`` correct process-steps output when parameters are entered
  interactively

patch version | description
------------- | --------------
2.3.1         | Specify numpy > 2 in setup.py file
2.3.2         | fix bug with target datas when loading station info

### v2.2

-  Fixed a bug in `lc2ms_py` in which big files caused a segmentation fault

### v2.1

- lcread() should work with numpy2.0 (partially verified)
- lc2SDS\_py and lc2ms\_py:
    - argparse limits station names to 5 characters, network names to 2
patch version | description
------------- | --------------
2.1.1         | `lc2ms_py`: fix `--version`, splitting of big files

## v2.0

- Renamed `lc2ms_weak` to `lc2ms_py`
- Renamed `lc2SDS_weak` to `lc2SDS_py`
- Added function `lcread:read_station()` and use in `lcread`
- Allow lc2SDS_weak to create/append to a StationXML file
- `lc2SDS_py` now sets quality flag to Q or D
- Various debugging

patch version | description
------------- | --------------
.0.post1      | include examples on pypi, require module sdpchainpy
.0.post2      | handle read length different from expected, removed `endDate` from instrument responses (except SPOBS1, and BBOBS1 pre-2012)

## v1.0

patch version | description
---------- | --------------
b0 | Combined lcheapo and lcheapo_obspy
.0 | Fixed some bugs associated with creation of the ProcessSteps class
.1 | Fixed bugs where lcheapo_obspy was still called, harmonized start_time in input file
.2 | Fixed a bug in accessing sdpchain library (affected lcinfo lcfix...)
.3 | Patch because 1.0.2 on PyPI was bad
.4 | Further cleaned references to sdpchain, changed setup.py to automatically find modules (manual system used before didn't put sdpchain/ on PyPI)
.5 | Changed required python version to 3.8 (some files use '=' specifier in f-strings).
.     | Integrated input_filename wildcard expansion into ProcessSteps.setup_path().
.     | lcinfo now tries to work even if there is no header
.     | Add example plots to lctest description in README.md
.     | Fixed bug in lc_test particle_motion part
.5.post1 | fixed bug in lc2SDS_weak argument handling
.6 | Removed `import future` (2.x module) because causes crashes with some Pythons
.7 | Fixed ProcessSteps calling bug in `sdpcat`
.8 | Added lccut script creation to `lcfix`, changed creation of process-steps.json
.  | to put all in one file, make backups of old versions

## v0.4 (0.74?)
First distributed

patch version | description
---------- | --------------
.2 | Add "--network" argument to lc2SDS_weak
.3 | Minor code tightening, better test case for read/write
.4 | Reorganized lc2SDS, add sdpchain compatibility
.5 | Fixed an error in SDS channel directory names
.6 | Puts correct band codes for given sampling rate
.7 | Added leapsecond handling to lc2SDS
.8 | Fixed lcread to only return data within the requested time bounds (inclusive start, exclusive end).  Also stops lc2SDS daily files from overlapping
.9 | lcread/plot no longer quits if there is a bad input file or date range is outside the range of some of the files

## v0.1

The Original

