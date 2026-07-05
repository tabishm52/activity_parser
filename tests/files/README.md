# Test fixture files

## Vendored FIT files

`garmin-edge-820-bike.fit` and `garmin-fenix-5-bike.fit` are copied from the [python-fitparse](https://github.com/dtcooper/python-fitparse) test suite (`tests/files/`, commit `d88bb699`), which is distributed under the MIT license.

## Hand-written XML files

Minimal fixtures written for this test suite, with round-number values chosen so tests can assert exact parsed output.
Each fixture documents its quirk in an XML comment, and the tests that reference it state the behavior it exercises.

`gpxtpx_v1.gpx`, `gpxdata.gpx`, `gpx10.gpx`, `unknown_extension.gpx`, `running.tcx`, and `cadence_collision.tcx` exercise the schema field tables in `xml_fields.py`: alternate/older extension namespaces, GPX 1.0's base (no-`<extensions>`) fields, a vendor extension this library doesn't recognize, and the base-schema-beats-extension collision rule.

`unknown_collision.tcx`, `mixed_content.tcx`, `vendor_type_attribute.tcx`, `duplicate_cadence.tcx`, `laps_only.tcx`, and `extra_vendor_type_attribute.tcx` exercise edge cases in `parse_tcx_gpx.py`'s traversal itself, rather than the field tables: colliding unknown-column names, mixed text-and-children elements, a non-`xsi:type` attribute literally named `type` (both within a trackpoint and at the root, for the `extra` dict), a literally duplicated element, and a trackpoint-free lap-only file.
