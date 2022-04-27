## v0.1

The Original

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