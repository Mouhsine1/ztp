""" ZTP API Web App
This script implements a simple API to serve the ZTP data object, using the
Bottle micro web framework and the Waitress HTTP server. There is a file serving
and listing API, as well as a CSV import and export API.
An AJAX web frontend app provides a GUI for data entry using these APIs. This
script validates the format of the data for every API call. Error messages of
failed API calls are presented in the GUI.

Author:  Tim Dorssers
Version: 1.0
"""

import io
import os
import csv
import sys
import json
import time
import bottle
import codecs
import logging
from collections import OrderedDict

HIDE = ['app.py', 'data.json', 'index.html', 'main.js', 'status.json',
        'style.css', 'script.py']

def log(req):
    """ Logs request from client to stderr """
    qs = '?' + req.query_string if len(req.query_string) else ''
    logging.info('%s - %s %s%s' % (req.remote_addr, req.method, req.path, qs))

def error(msg):
    """ Sends HTTP 500 with error message string by raising HTTPResponse """
    raise bottle.HTTPResponse(body=json.dumps(str(msg)), status=500,
                              headers={'Content-type': 'application/json'})

@bottle.route('/')
@bottle.route('/<filename>')
def index(filename='index.html'):
    """ Frontend GUI app """
    log(bottle.request)
    return bottle.static_file(filename, root='.')

@bottle.get('/file/<filepath:path>')
def get_file(filepath):
    """ Serves files and subfolders """
    log(bottle.request)
    return bottle.static_file(filepath, root='.')

@bottle.delete('/file/<filepath:path>')
def delete_file(filepath):
    """ Removes specified file """
    log(bottle.request)
    if any(name in filepath for name in HIDE):
        error('Cannot remove %s' % filepath)
    else:
        try:
            os.remove(filepath)
        except OSError as e:
            error(e)

@bottle.post('/file')
def post_file():
    """ Handles form data for file uploading """
    log(bottle.request)
    folder = bottle.request.forms.get('folder')
    upload = bottle.request.files.get('upload')
    try:
        if folder and not os.path.exists(folder):
            os.makedirs(folder)

        upload.save(os.path.join(folder, upload.filename), overwrite=True)
    except (OSError, IOError) as e:
        error(e)

@bottle.route('/list')
def get_list():
    """ Compiles a list of files and sends it to the web server """
    log(bottle.request)
    flist = []
    for root, dirs, files in os.walk('.'):
        # Don't visit hidden directories
        dirs[:] = [name for name in dirs if not name.startswith('.')]
        # Exclude specific and hidden files
        for name in files:
            if not name in HIDE and not name.startswith('.'):
                fname = os.path.join(root, name)
                fsize = os.path.getsize(fname)
                flist.append({'file': fname.replace('\\', '/'), 'size': fsize})

    # Prepare response header
    bottle.response.content_type = 'application/json'
    bottle.response.expires = 0
    bottle.response.set_header('Pragma', 'no-cache')
    bottle.response.set_header('Cache-Control',
                               'no-cache, no-store, must-revalidate')
    return json.dumps(flist)

@bottle.get('/data')
def get_data():
    """ Parses JSON file into an OrderedDict and sends it to the web server """
    log(bottle.request)
    # Prepare response header
    bottle.response.content_type = 'application/json'
    bottle.response.expires = 0
    bottle.response.set_header('Pragma', 'no-cache')
    bottle.response.set_header('Cache-Control',
                               'no-cache, no-store, must-revalidate')
    # Load, validate and send JSON data
    try:
        if os.path.exists('data.json'):
            with open('data.json') as infile:
                data = json.load(infile, object_pairs_hook=OrderedDict)
                validate(data)
                return json.dumps(data)
        else:
            return json.dumps([{}])

    except (ValueError, IOError) as e:
        error(e)

@bottle.post('/data')
def post_data():
    """ Parses posted JSON data into an OrderedDict and writes to file """
    log(bottle.request)
    if bottle.request.content_type == 'application/json':
        # Load, validate and write JSON data
        try:
            data = json.loads(bottle.request.body.getvalue(),
                              object_pairs_hook=OrderedDict)
            validate(data)
            with open('data.json', 'w') as outfile:
                json.dump(data, outfile, indent=4)
        except (ValueError, IOError) as e:
            error(e)

@bottle.get('/csv')
def get_csv():
    """ Converts JSON file to CSV and sends it to web server """
    log(bottle.request)
    with open('data.json') as infile:
        data = json.load(infile, object_pairs_hook=OrderedDict)
        validate(data)
        # Flatten JSON data
        flat_data = []
        for dct in data:
            flat = OrderedDict()
            for k in dct.keys():
                if isinstance(dct[k], OrderedDict):
                    for kk in dct[k].keys():
                        flat[str(k) + '/' + str(kk)] = dct[k][kk]
                else:
                    flat[k] = dct[k]
            flat_data.append(flat)

        # Find column names
        columns = [k for row in flat_data for k in row.keys()]
        columns = list(OrderedDict.fromkeys(columns).keys())
        # Write CSV to buffer
        if sys.version_info >= (3, 0, 0):
            csvbuf = io.StringIO()
        else:
            csvbuf = io.BytesIO()

        writer = csv.DictWriter(csvbuf, fieldnames=columns, delimiter=';')
        writer.writeheader()
        writer.writerows(flat_data)
        # Prepare response header
        bottle.response.content_type = 'text/csv'
        bottle.response.expires = 0
        bottle.response.set_header('Pragma', 'no-cache')
        bottle.response.set_header('Cache-Control',
                                   'no-cache, no-store, must-revalidate')
        bottle.response.set_header('Content-Disposition',
                                   'attachment; filename="export.csv"')
        return csvbuf.getvalue()

@bottle.post('/csv')
def post_data():
    """ Converts uploaded CSV to JSON data and writes to file """
    log(bottle.request)
    upload = bottle.request.files.get('upload')
    reader = csv.reader(codecs.iterdecode(upload.file, 'utf-8'), delimiter=';')
    headers = next(reader)
    data = []
    for row in reader:
        dct = OrderedDict(zip(headers, row))
        # Construct original cubic data structure
        cubic = OrderedDict()
        for k in dct.keys():
            kk = k.split('/')
            if dct[k] and len(kk) == 2:
                if kk[0] in cubic:
                    cubic[kk[0]].update(OrderedDict([(kk[1], dct[k])]))
                else:
                    cubic[kk[0]] = OrderedDict([(kk[1], dct[k])])
            else:
                if dct[k] == "True":
                    cubic[k] = True
                elif dct[k]:
                    cubic[k] = dct[k]
        data.append(cubic)

    # Validate and write JSON data
    try:
        validate(data)
        with open('data.json', 'w') as outfile:
            json.dump(data, outfile, indent=4)
    except (ValueError, IOError) as e:
        error(e)

@bottle.get('/log')
def log_get():
    log(bottle.request)
    logbuf = []
    try:
        if os.path.exists('status.json'):
            with open('status.json') as infile:
                logbuf = json.load(infile)
    except (ValueError, IOError) as e:
        error(e)

    # Prepare response header
    bottle.response.content_type = 'application/json'
    bottle.response.expires = 0
    bottle.response.set_header('Pragma', 'no-cache')
    bottle.response.set_header('Cache-Control',
                               'no-cache, no-store, must-revalidate')
    # Update log buffer from URL parameter or send log buffer if no parameter 
    if 'msg' in bottle.request.query:
        try:
            msg = json.loads(bottle.request.query.msg)
            if not isinstance(msg, dict):
                error('Expected JSON object')

            msg['ip'] = bottle.request.remote_addr
            msg['time'] = time.strftime('%x %X')
            logbuf.append(msg)
            # Write log buffer to file
            with open('status.json', 'w') as outfile:
                json.dump(logbuf, outfile, indent=4)
        except (ValueError, IOError) as e:
            error(e)

        return '\n'
    else:
        return json.dumps(logbuf)

@bottle.delete('/log')
def log_delete():
    log(bottle.request)
    # Just write empty list to file
    try:
        with open('status.json', 'w') as outfile:
            json.dump([], outfile)
    except (ValueError, IOError) as e:
        error(e)

def validate(data):
    """ Validates data and raises ValueError if invalid """
    if not isinstance(data, list):
        raise ValueError('Expecting JSON array of objects')

    num_defaults = 0
    for my in data:
        if not isinstance(my, OrderedDict):
            raise ValueError('Expecting JSON array of objects')

        if 'stack' in my and not isinstance(my['stack'], OrderedDict):
            raise ValueError('Stack must be JSON object')

        if 'subst' in my and not isinstance(my['subst'], OrderedDict):
            raise ValueError('Subst must be JSON object')

        num_obj = [len(v) for v in my.values() if isinstance(v, OrderedDict)]
        if 0 in num_obj:
            raise ValueError('Empty JSON object not allowed')

        empty = [k for k in my if not k or k.isspace()]
        if len(empty):
            raise ValueError('Empty JSON keys not allowed')

        if not 'stack' in my:
            num_defaults += 1

    if num_defaults > 1:
        raise ValueError('Maximum of one object without stack key is allowed')

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    bottle.run(host='0.0.0.0', port=8080, server='waitress')
