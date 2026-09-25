"""Measure phase_shift_<f>hz_rad: max |phase(run) - phase(baseline)| along the scan line.

usage: phase_shift.py --freq 1|10 --baseline D011 <run-outputs-dir>
Reads phase_<f>hz.csv from the run's outputs.dir and from the baseline run, prints one JSON
object with the measure name and value. `campaign collect` merges it into qoi.json.
"""
