# Test fixture files

Organized into `fit/`, `gpx/`, and `tcx/` subdirectories by format.

## Vendored FIT files

`garmin-edge-820-bike.fit`, `garmin-fenix-5-bike.fit`, and `garmin-fenix-5-run.fit` are copied from the [python-fitparse](https://github.com/dtcooper/python-fitparse) test suite (`tests/files/`, commit `d88bb699`), which is distributed under the MIT license.

`DeveloperData.fit` is copied from the [fitdecode](https://github.com/polyvertex/fitdecode) test suite (`tests/files/`, commit `130028b0`), which is distributed under the MIT license.
It's a hand-crafted 178-byte sample exercising a Connect IQ developer field (`doughnuts_earned`).
Its `record` messages have no `timestamp` field.

## Hand-written GPX & TCX files

Minimal XML fixtures written for this test suite, with round-number values chosen so tests can assert exact parsed output.
Each fixture documents its quirk in an XML comment, and the tests that reference it state the behavior it exercises.
