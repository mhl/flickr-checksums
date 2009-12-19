#!/usr/bin/env python2.5

# Copyright 2009 Mark Longair

#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

# You might use this, for example, as:
#
#   find ~/photos/ -name '*.jpg' -print0 | xargs -0 ./find-not-uploaded.py

import os
import sys
import re
import xml
import tempfile
from subprocess import call, Popen, PIPE
from optparse import OptionParser

all_filenames = sys.argv[1:]

parser = OptionParser(usage="Usage: %prog [OPTION] [FILE]...")
parser.add_option('-v', '--verbose', dest='verbose', default=False,
                  action='store_true',
                  help='Turn on verbose output')
options,args = parser.parse_args()

for filename in args:
    result = Popen(["md5sum",filename],stdout=PIPE).communicate()[0]
    md5sum = re.sub(' .*$','',result).strip()
    if options.verbose:
        print "filename was: "+filename
        print " with md5sum: "+md5sum
    p = Popen(["./flickr-checksum-tags.py","-m",md5sum],stdout=PIPE)
    c = p.communicate()
    if 0 == p.returncode:
        if options.verbose:
            print "  ... already uploaded"
            print "  "+c[0].strip()
    elif 3 == p.returncode:
        if options.verbose:
            print "  ... multiple copies uploaded"
    else:
        if options.verbose:
            print "  ... not uploaded"
        else:
            print filename
