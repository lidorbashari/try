"""Runs the design-era UI suites (app_test/run_tests.py, run_s7.py) against the RELEASE file SP/mashup-lab.html
with the real engine: build.build() is replaced by a copy of the release document.
usage: python3 qa/run_ui_suites.py run_tests.py|run_s7.py"""
import os, runpy, shutil, sys, json
QA = os.path.dirname(os.path.abspath(__file__)); LAB = os.path.dirname(QA); SP = os.path.dirname(LAB); APPT = os.path.join(LAB, "app_test")
sys.path.insert(0, APPT)
import build as B
def fake(engine="real", out=None):
    out = out or os.path.join(APPT, f"out_{engine}.html"); shutil.copy(os.path.join(SP, "mashup-lab.html"), out)
    return out, os.path.join(LAB, "data.json"), len(json.load(open(os.path.join(LAB, "data.json"), encoding="utf-8")))
B.build = fake
name = sys.argv[1]; sys.argv = [os.path.join(APPT, name), "real"]
runpy.run_path(os.path.join(APPT, name), run_name="__main__")
