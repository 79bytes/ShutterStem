'''Simple classes for talking with CouchDB, as a client or as an external process'''

import sys
import json
import httplib
import urllib, urlparse


class Database(object):
    def __init__(self, url):
        self.url = url
    
    def url_for(self, path, query=None):
        if type(path) not in (str, unicode):
            path = '/'.join(path)
        
        if query:
            path += "?" + urllib.urlencode([
                (key[1:], json.dumps(value)) if key[0] == '$' else (key, value) for (key,value) in query.iteritems()
            ])
        
        return "%s/%s" % (self.url, path)
    
    def http(self, method, obj, path, query=None):
        url = self.url_for(path, query)
        url_parts = urlparse.urlsplit(url)
        
        Con = httplib.HTTPSConnection if url_parts.scheme == 'https' else httplib.HTTPConnection
        conn = Con(url_parts.netloc)
        conn.request(method.upper(), url, json.dumps(obj) if obj else None, {'Content-Type':"application/json"})
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())
    
    def get(self, path='', query=None):
        status, result = self.http('GET', None, path, query)
        return result if status == 200 else None
    
    def read(self, id):
        status, result = self.http('GET', None, id)
        if status != 200:
            raise IOError(status, result['error'], id)
        return result
    
    def delete(self, doc):
        status, result = self.http('DELETE', None, doc['_id'], {'rev':doc['_rev']})
        if status != 200:
            raise IOError(status, result['error'], id)
        doc['_deleted'] = True
        doc['_rev'] = result['rev']
    
    def write(self, doc):
        status, result = self.http('PUT', doc, doc['_id'])
        if status != 201:
            raise IOError(status, result['error'], doc['_id'])
        doc['_rev'] = result['rev']


# see http://wiki.apache.org/couchdb/ExternalProcesses for configuration instructions
# and http://www.davispj.com/2010/09/26/new-couchdb-externals-api.html for The Future (?)
class External(object):
    def run(self):
        line = sys.stdin.readline()
        while line:
            try:
                response = self.process(json.loads(line))
            except Exception:
                response = {'code':500, 'json':{'error':True, 'reason':"Internal error processing request"}}
            sys.stdout.write("%s\n" % json.dumps(response))
            sys.stdout.flush()
            line = sys.stdin.readline()
    
    def process(self, req):
        return {'json':{'ok':True}}
