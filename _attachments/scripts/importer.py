#! /usr/bin/python
from __future__ import with_statement   # needed under Python 2.5 (Leopard default)


import couch

from time import sleep
import os
import json
import uuid

from threading import Thread
from Queue import Queue

class Importer(object):
    def __init__(self, db_url, source_id, folder):
        self._cancelled = False
        self._done = False
        self._files = Queue()
        self._image_docs = Queue(maxsize=30)
        self._imported_ids = Queue()
        
        def find_new_files():
            for (dirpath, dirnames, filenames) in os.walk(folder):
                for filename in filenames:
                    if self._cancelled:
                        break
                    if filename[0] == '.':
                        continue
                    
                    full_path = os.path.join(dirpath, filename)
                    rel_path = os.path.relpath(full_path, folder)
                    identifiers = {'relative_path':{'source':{'_id':source_id}, 'path':rel_path}}
                    if not image_with_identifiers(identifiers):     # TODO: implement image_with_identifiers
                        self._files.put(full_path)
                
                if self._cancelled:
                    break
            self._files.put(None)
                
        
        def get_file_docs():
            while not self._cancelled:
                file = self._files.get()
                if not file:
                    break
                doc = doc_for_file(file)        # TODO: implement doc_for_file, image_with_identifiers
                if doc and not image_with_identifiers(doc['identifiers']):  
                    self._image_docs.put(doc)
                self._files.task_done()
            self._image_docs.put(None)
        
        def upload_docs():
            while not self._cancelled:
                doc = self._image_docs.get()
                if not doc:
                    break
                doc_id = write_new_doc(doc)     # TODO: implement write_new_doc
                self._imported_ids.put(doc_id)
                self._image_docs.task_done()
            self._imported_ids.put(None)
            self._done = True
        
        self._find_files = Thread(target=find_new_files)
        self._find_files.daemon = True
        self._find_files.start()
        self._get_file_docs = Thread(target=get_file_docs)
        self._get_file_docs.daemon = True
        self._get_file_docs.start()
        self._upload_docs = Thread(target=upload_docs)
        self._upload_docs.daemon = True
    
    def begin(self):
        self._upload_docs.start()
    
    def cancel(self, remove=True):
        self._cancelled = True
        
        if self._find_files.is_alive():
            self._find_files.join()
        if self._get_file_docs.is_alive():
            self._get_file_docs.join()
        if self._upload_docs.is_alive():
            self._upload_docs.join()
        
        def delete_docs():
            while True:
                doc_id = self._imported_ids.pop()
                if not doc_id:
                    break
                delete_doc(doc_id)      # TODO: implement delete_doc
        Thread(target=delete_docs).start()
    
    def status(self):
        if self._cancelled:
            verb = 'cancel'
        elif self._done:
            verb = 'done'
        elif self._upload_docs.is_alive():
            verb = 'import+scan' if self._find_files.is_alive() else 'import'
        else:
            verb = 'wait+scan' if self._find_files.is_alive() else 'wait'
        
        return {
            'imported': self._imported_ids.qsize() - 1 if verb == 'done' else 0,
            'remaining': self._files.qsize() + self._image_docs.qsize() - 1 if (verb == 'import' or verb == 'wait') else 0,
            'verb': verb,
            # TODO: self._image_docs preview
        }


class ImportManager(couch.External):
    def __init__(self):
        self.imports = {}
    
    def process_folder(self, req):
        source_id = req['path'][2]
        token = req['query'].get('token', None)
        helper = req['query'].get('utility', None)
        if not token or not helper or not source_id:
            return {'code':400, 'json':{'error':True, 'reason':"Required parameter(s) missing"}}
        
        # check that the request is not forged
        with open(helper, 'r') as f:
            first_chunk = f.read(4096)  # token required in first 4k
            if first_chunk.find("<!-- SHUTTERSTEM-TOKEN(%s)TOKEN-SHUTTERSTEM -->" % token) == -1:
                raise Exception()
        
        if source_id in self.imports:
            return {'code':409, 'json':{'error':True, 'reason':"An import is already in progress for this source"}}
        
        info = self.imports[source_id] = {}
        info['token'] = uuid.uuid4().hex
        info['folder'] = os.path.dirname(helper)
        info['importer'] = Importer(None, source_id, info['folder'])
        
        return {'code':202, 'json':{'ok':True, 'message':"Import of '%s' may now start." % info['folder'], 'token':info['token']}}
    
    def process_cancel(self, req):
        source_id = req['path'][2]
        token = req['query'].get('token', None)
        if not token or not source_id:
            return {'code':400, 'json':{'error':True, 'reason':"Required parameter(s) missing"}}
        
        if source_id not in self.imports:
            return {'code':404, 'json':{'error':True, 'reason':"No import is in progress for this source"}}
        
        info = self.imports[source_id]
        if token != info['token']:
            raise Exception()
        
        info['importer'].cancel()
        return {'code':202, 'json':{'ok':True, 'message':"Import is cancelling"}}
        
    def process(self, req):
        if req['method'] == 'POST' and req['path'][3] == "folder":
            try:
                return self.process_folder(req)
            except Exception:
                sleep(2.5)    # slow down malicious local scanning
                return {'code':400, 'json':{'error':True, 'reason':"Bad request"}}
        
        elif req['method'] == 'POST' and req['path'][3] == "cancel":
            try:
                return self.process_folder(req)
            except Exception:
                sleep(0.5)
                return {'code':400, 'json':{'error':True, 'reason':"Bad request"}}
        
        #return {'body': "<h1>Hello World!</h1>\n<pre>%s</pre>" % json.dumps(req, indent=4)}
        elif req['method'] == 'GET':
            source_id = req['path'][2]
            if source_id not in self.imports:
                return {'code':404, 'json':{'error':True, 'reason':"No import is in progress for this source"}}
            
            status = self.imports[source_id].status()
            return {'json':status}
        
        return {'code':400, 'json':{'error':True, 'reason':"Bad request"}}
        

if __name__ == "__main__":
    import_server = ImportManager()
    import_server.run()