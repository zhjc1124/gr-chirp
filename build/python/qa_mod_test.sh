#!/bin/sh
export VOLK_GENERIC=1
export GR_DONT_LOAD_PREFS=1
export srcdir=/home/test/Documents/gr-chirp/python
export PATH=/home/test/Documents/gr-chirp/build/python:$PATH
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH
export PYTHONPATH=/home/test/Documents/gr-chirp/build/swig:$PYTHONPATH
/usr/bin/python2 /home/test/Documents/gr-chirp/python/qa_mod.py 
