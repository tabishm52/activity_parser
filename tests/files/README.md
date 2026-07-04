# Test fixture files

## Vendored FIT files

`garmin-edge-820-bike.fit` and `garmin-fenix-5-bike.fit` are copied from the
[python-fitparse](https://github.com/dtcooper/python-fitparse) test suite
(`tests/files/`, commit `d88bb6997138c38d0c578aeaaf4108df0711d1f6`), which is
distributed under the MIT license.

## Hand-written XML files

`sample.tcx`, `sample.gpx`, `no_position.tcx`, `multi_segment.gpx`,
`no_time.tcx`, and `no_time.gpx` are minimal fixtures written for this test
suite, with round-number values chosen so tests can assert exact parsed
output. `sample.tcx` and `sample.gpx` each include one trackpoint with a
duplicated timestamp to exercise duplicate-index handling. `no_time.tcx` and
`no_time.gpx` each include two consecutive trackpoints missing their time
element, to exercise dropping NaT-indexed rows instead of collapsing them
together as duplicates.
