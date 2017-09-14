#! /usr/bin/env python
#
# Read a file containing cases and load them into the database
#
# The file(s) can be provided as the arguments like so:
#
# load_birds.py bird_file.tsv bird_file2.tsv
#
# Or as a pipe like this, using "-" as the argument:
#
# cat bird_file.tsv | load_birds.py -
#
# The first line (field names) will be discarded
# remaining lines must be tab-separated, in the following order:
# id
# date (MM/DD/YYYY)
# long (decimal degrees)
# lat (decimal degrees)
# species

import sys
import optparse
import logging

import dycast
from services import logging_service


logging_service.init_logging()

usage = "usage: %prog [options] datafile.tsv"
required = "srid".split()

p = optparse.OptionParser(usage)
p.add_option('--config', '-c', 
            default="./dycast.config", 
            help="load config file FILE", 
            metavar="FILE")
p.add_option('--srid')

options, arguments = p.parse_args()

for r in required:
    if options.__dict__[r] is None:
        logging.error("Parameter %s required", r)
        sys.exit(1)

config_file = options.config
dycast.read_config(config_file)
dycast.init_db()

user_coordinate_system = options.srid

# If arguments includes multiple filenames, fileinput will handle them all

for file in arguments:
    (lines_read, lines_processed, lines_loaded, lines_skipped) = dycast.load_case_file(user_coordinate_system, file)

