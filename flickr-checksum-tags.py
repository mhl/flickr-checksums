#!/usr/bin/env python2.5

# This depends on a couple of packages:
#   apt-get install python-pysqlite2 python-flickrapi

import os
import sys
import re
import xml
import tempfile
from subprocess import call, Popen, PIPE
import flickrapi
from optparse import OptionParser
from pysqlite2 import dbapi2 as sqlite

flickr_api_filename = os.path.join(os.environ['HOME'],'.flickr-api')
if not os.path.exists(flickr_api_filename):
    print "You must put your Flickr API key and secret in "+flickr_api_filename

db_filename = os.path.join(os.environ['HOME'],'.flickr-photos-checksummed.db')
connection = sqlite.connect(db_filename)
cursor = connection.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS done ( photo_id text unique )")

def already_done(photo_id):
    cursor.execute("SELECT * FROM done WHERE photo_id = ?", (photo_id,))
    return len(cursor.fetchall()) > 0

def add_to_done(photo_id):
    cursor.execute("INSERT INTO done ( photo_id ) VALUES ( ? )", (photo_id,))
    connection.commit()

configuration = {}
for line in open(flickr_api_filename):
    if len(line.strip()) == 0:
        continue
    m = re.search('\s*(\S+)\s*=\s*(\S+)\s*$',line)
    if m:
        configuration[m.group(1)] = m.group(2)
    if not m:
        print "Each line of "+flickr_api_filename+" must be either empty"
        print "or of the form 'key = value'"
        sys.exit(2)
    continue

if not ('api_key' in configuration and 'api_secret' in configuration):
    print "Both api_key and api_secret must be defined in "+flickr_api_filename

# There are more details about the meaning of these size
# codes here:
#
#   http://www.flickr.com/services/api/misc.urls.html

valid_size_codes = ( "s", "t", "m", "-", "b", "o" )
v = [ '"'+x+'"' for x in valid_size_codes ]
valid_size_codes_sentence = ", ".join(v[0:-1]) + " or " + v[-1]

parser = OptionParser(usage="Usage: %prog [OPTIONS]")
parser.add_option('-a', '--add-tags', dest='add_tags',
                  metavar='USERNAME',
                  help='add checksum machine tags for [USERNAME]\'s photos')
parser.add_option('-m', dest='md5',
                  metavar='MD5SUM',
                  help='find my photo on Flickr with MD5sum [MD5SUM]')
parser.add_option('-s', dest='sha1',
                  metavar='SHA1SUM',
                  help='find my photo on Flickr with SHA1sum [SHA1SUM]')
parser.add_option('-p', dest='photo_page', default=False, action='store_true',
                  help='Output the photo page URL (the default with -m and -s)')
parser.add_option('--size',dest='size',metavar='SIZE',
                   help='Output the URL for different sized images ('+valid_size_codes_sentence+')')

options,args = parser.parse_args()

mutually_exclusive_options = [ options.add_tags, options.md5, options.sha1 ]

if 1 != len([x for x in mutually_exclusive_options if x]):
    print "You must specify exactly one of '-a', '-m' or 's':"
    parser.print_help()
    sys.exit(1)

if options.photo_page and options.size:
    print "options.photo_page is "+str(options.photo_page)
    print "You can specify at most one of -p and --size"
    parser.print_help()
    sys.exit(1)

just_photo_page_url = not options.size

if options.size and (options.size not in valid_size_codes):
    print "The argument to --size must be one of: "+valid_size_codes_sentence

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

checksum_pattern = "[0-9a-f]{32,40}"

md5_machine_tag_prefix = "checksum:md5="
sha1_machine_tag_prefix = "checksum:sha1="

# Return a dictionary with any machine tag checksums found for a photo
# element:
def get_photo_checksums(photo):
    info_result = flickr.photos_getInfo(photo_id=photo.attrib['id'])
    result = {}
    for t in info_result.getchildren()[0].find('tags'):
        m_md5 = re.search('^'+md5_machine_tag_prefix+'('+checksum_pattern+')$',t.attrib['raw'])
        if m_md5 and len(m_md5.group(1)) == 32:
            print "Got MD5sum machine tag"
            result['md5'] = m_md5.group(1)
        m_sha1 = re.search('^'+sha1_machine_tag_prefix+'('+checksum_pattern+')$',t.attrib['raw'])
        if m_sha1 and len(m_sha1.group(1)) == 40:
            print "Got SHA1sum machine tag"
            result['sha1'] = m_sha1.group(1)
    return result

def info_to_url(info_result,size=""):
    a = info_result.getchildren()[0].attrib
    if size in ( "", "-" ):
        return 'http://farm%s.static.flickr.com/%s/%s_%s.jpg' %  (a['farm'], a['server'], a['id'], a['secret'])
    elif size in ( "s", "t", "m", "b" ):
        return 'http://farm%s.static.flickr.com/%s/%s_%s_%s.jpg' %  (a['farm'], a['server'], a['id'], a['secret'], size)
    elif size == "o":
        return 'http://farm%s.static.flickr.com/%s/%s_%s_o.%s' %  (a['farm'], a['server'], a['id'], a['originalsecret'], a['originalformat'])
    else:
        raise Exception, "Unknown size ("+size+") passed to info_to_url()"

if options.md5 or options.sha1:
    # Setup the tag to search for:
    if options.md5:
        if not re.search('^'+checksum_pattern+'$',options.md5):
            print "The MD5sum ('"+options.md5+"') was malformed."
            print "It must be 32 letters long, each one of 0-9 or a-f."
            sys.exit(1)
        search_tag = md5_machine_tag_prefix + options.md5
    else:
        if not re.search('^'+checksum_pattern+'$',options.sha1):
            print "The SHA1sum ('"+options.sha1+"') was malformed."
            print "It must be 40 letters long, each one of 0-9 or a-f."
            sys.exit(1)
        search_tag = sha1_machine_tag_prefix + tag
    photos = flickr.photos_search(user_id="me",tags=search_tag)
    photo_elements = photos.getchildren()[0]
    if 1 != len(photo_elements):
        raise Exception, "Expected exactly one result searching for tag "+search_tag+"; actually got "+str(len(photo_elements))
    photo = photo_elements[0]
    photo_id = photo.attrib['id']
    photo_info = flickr.photos_getInfo(photo_id=photo_id)
    if just_photo_page_url:
        user_info = flickr.people_getInfo(user_id=photo.attrib['owner'])
        print user_info.getchildren()[0].find('photosurl').text+photo_id
    else:
        print info_to_url(photo_info,size=options.size)
else:
    nsid = get_nsid(options.add_tags)
    if not nsid:
        print "Couldn't find the username or alias '"+options.add_tags

    print "Got nsid: %s for '%s'" % ( nsid, options.add_tags )

    user_info = flickr.people_getInfo(user_id=nsid)
    photos_url = user_info.getchildren()[0].find('photosurl').text

    per_page = 100
    page = 1

    while True:
        photos = flickr.photos_search(user_id=nsid, per_page=str(per_page), page=page, media='photo' )
        photo_elements = photos.getchildren()[0]
        print "----------------------------------------------------------------"
        for photo in photo_elements:
            title = photo.attrib['title']
            print "====="+title+"====="
            id = photo.attrib['id']
            if already_done(id):
                continue
            print "Photo page URL is: "+photos_url+id
            info_result = flickr.photos_getInfo(photo_id=id)
            # Check if the checksums are already there:
            existing_checksums = get_photo_checksums(photo)
            if ('md5' in existing_checksums) and ('sha1' in existing_checksums):
                # Then there's no need to download the image...
                pass
            else:
                # Otherwise fetch the original image to a temporary file,
                # take its checksums and set those tags:
                farm_url = info_to_url(info_result,'o')
                f = tempfile.NamedTemporaryFile()
                f.close()
                print "farm_url is: "+farm_url
                call(["curl","--location","-o",f.name,farm_url])
                md5sum_result = Popen(["md5sum",f.name],stdout=PIPE).communicate()[0]
                sha1sum_result = Popen(["sha1sum",f.name],stdout=PIPE).communicate()[0]
                m = re.search('^('+checksum_pattern+')',md5sum_result.strip())
                if not m:
                    raise Exception, "Result from md5sum was unexpected: "+md5sum_result
                real_md5sum = m.group(1)
                m = re.search('^('+checksum_pattern+')',sha1sum_result.strip())
                if not m:
                    raise Exception, "Result from sha1sum was unexpected: "+sha1sum_result
                real_sha1sum = m.group(1)
                print "Calculated MD5: "+real_md5sum
                print "Calculated SHA1: "+real_sha1sum
                print "Setting tags..."
                flickr.photos_addTags(photo_id=id, tags=md5_machine_tag_prefix+real_md5sum)
                flickr.photos_addTags(photo_id=id, tags=sha1_machine_tag_prefix+real_sha1sum)
                print "... done.  Removing temporary file."
                call(["rm",f.name])
            add_to_done(id)
        if len(photo_elements) < per_page:
            break
        page += 1
