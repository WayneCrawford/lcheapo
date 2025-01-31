# lcheapo

Viewing and modifying LCHEAPO-2000 OBS data

## Overview

### Command-line programs

Type ``{command} -h`` to get a list of parameters and options

#### Programs that don't modify files

| Program     | description                                           |
| ----------- | ----------------------------------------------------- |
| lcdump      | dump raw information from LCHEAPO files               |
| lcinfo      | return basic information about an LCHEAPO file        |
| lcplot      | plot an LCHEAPO file                                  |
| lc_examples | create a directory with examples of lcplot and lctest |

#### Programs that modify files

These programs integrate the [sdpchain](https://github.com/WayneCrawford/sdpchainpy)
module, to document the processing workflow.

| Program     | description                                                                   |
| ----------- | ----------------------------------------------------------------------------- |
| lccut       | extract section of an LCHEAPO file                                            |
| lcfix       | fix common bugs in an LCHEAPO file                                            |
| lcheader    | create an LCHEAPO header + directory                                          |
| lc2ms_py    | converts LCHEAPO file to basic miniSEED files                                 |
| lc2SDS_py   | converts LCHEAPO file to SeisComp Data Structure, with basic drift correction |
