# Test fixture files

## Vendored FIT files

`garmin-edge-820-bike.fit` and `garmin-fenix-5-bike.fit` are copied from the [python-fitparse](https://github.com/dtcooper/python-fitparse) test suite (`tests/files/`, commit `d88bb699`), which is distributed under the MIT license.

## Hand-written XML files

Minimal fixtures written for this test suite, with round-number values chosen so tests can assert exact parsed output:

- `sample.tcx`, `sample.gpx` — include a trackpoint with a duplicated timestamp, to exercise duplicate-index handling.
- `no_position.tcx` — trackpoints with no `<Position>` element.
- `multi_segment.gpx` — a track split across multiple `<trkseg>` elements, which should merge into one records frame.
- `no_time.tcx`, `no_time.gpx` — include two consecutive trackpoints missing their time element, to exercise dropping NaT-indexed rows instead of collapsing them together as duplicates.
- `mixed_offset.tcx`, `mixed_offset.gpx` — trackpoints with mixed UTC-offset and naive timestamps, to exercise normalizing to UTC.
