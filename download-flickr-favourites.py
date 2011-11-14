#!/usr/bin/env python

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

# This depends on a couple of packages:
#   apt-get install python-flickrapi

import os
import sys
import re
import xml
import tempfile
import time
from subprocess import call, Popen, PIPE
import flickrapi
from optparse import OptionParser
from common import *
import urllib2
import contextlib

parser = OptionParser(usage="Usage: %prog [OPTIONS] <FLICKR-USERNAME>")
options,args = parser.parse_args()

if len(args) != 1:
    parser.print_help()
    sys.exit(1)

flickr = flickrapi.FlickrAPI(configuration['api_key'],configuration['api_secret'])

(token, frob) = flickr.get_token_part_one(perms='write')
if not token:
    raw_input("Press 'Enter' after you have authorized this program")
flickr.get_token_part_two((token, frob))

# Return the Flickr NSID for a username or alias:
def get_nsid(username_or_alias):
    try:
        # If someone provides their real username (i.e. [USERNAME] in
        # "About [USERNAME]" on their profile page, then this call
        # should work:
        user = flickr.people_findByUsername(username=username_or_alias)
    except flickrapi.exceptions.FlickrError:
        # However, people who've set an alias for their Flickr URLs
        # sometimes think their username is that alias, so try that
        # afterwards.  (That's [ALIAS] in
        # http://www.flickr.com/photos/[ALIAS], for example.)
        try:
            username = flickr.urls_lookupUser(url="http://www.flickr.com/people/"+username_or_alias)
            user_id = username.getchildren()[0].getchildren()[0].text
            user = flickr.people_findByUsername(username=user_id)
        except flickrapi.exceptions.FlickrError, e:
            return None
    return user.getchildren()[0].attrib['nsid']

def original_available(info_result):
    return 'originalsecret' in info_result.getchildren()[0].attrib

def info_to_url(info_result,size=""):
    a = info_result.getchildren()[0].attrib
    if size in ( "", "-" ):
        return ('jpg', 'http://farm%s.static.flickr.com/%s/%s_%s.jpg' %  (a['farm'], a['server'], a['id'], a['secret']))
    elif size in ( "s", "t", "m", "b" ):
        return ('jpg', 'http://farm%s.static.flickr.com/%s/%s_%s_%s.jpg' %  (a['farm'], a['server'], a['id'], a['secret'], size))
    elif size == "o":
        return (a['originalformat'], 'http://farm%s.static.flickr.com/%s/%s_%s_o.%s' %  (a['farm'], a['server'], a['id'], a['originalsecret'], a['originalformat']))
    else:
        raise Exception, "Unknown size ("+size+") passed to info_to_url()"

nsid = get_nsid(args[0])
if not nsid:
    print "Couldn't find the username or alias '"+args[0]
    sys.exit(1)

print "Got nsid: %s for '%s'" % ( nsid, args[0] )

per_page = 100
page = 1

while True:

    response = flickr.favorites_getPublicList(user_id=nsid, per_page=per_page, page=page)

    photo_elements = response.getchildren()[0]
    for photo in photo_elements:
        title = photo.attrib['title']
        photo_id = photo.attrib['id']
        print "Title:", title
        info_result = flickr.photos_getInfo(photo_id=photo_id)
        if original_available(info_result):
            size = 'o'
        else:
            size = 'b'
        photo_format, farm_url = info_to_url(info_result, size)
        print "  Farm URL:", farm_url
        safe_title = re.sub('[ /]', '_', title)
        filename = "%s-%s-%s.%s" % (size, photo_id, safe_title, photo_format)
        if not os.path.exists(filename):
            with contextlib.closing(urllib2.urlopen(farm_url)) as ifp:
                with open(filename, "w") as ofp:
                    ofp.write(ifp.read())

    if len(photo_elements) < per_page:
        break
    page += 1
