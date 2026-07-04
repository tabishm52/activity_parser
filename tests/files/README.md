# Test fixture files

## Vendored FIT files

`garmin-edge-820-bike.fit` and `garmin-fenix-5-bike.fit` are copied from the [python-fitparse](https://github.com/dtcooper/python-fitparse) test suite (`tests/files/`, commit `d88bb699`), which is distributed under the MIT license.

## Hand-written XML files

Minimal fixtures written for this test suite, with round-number values chosen so tests can assert exact parsed output.
Each fixture documents its quirk in an XML comment, and the tests that reference it state the behavior it exercises.
