"""Run with python3 -m socratic_prototype.server. Loopback-only local server."""
import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .store import Store
from .validation import ValidationError, turtle, shacl_report
from .language import configuration as language_configuration
from .tasks import get_task,available_tasks

ROOT=Path(__file__).resolve().parent
STATIC=ROOT/'static'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass  # Avoid persisting participant text or session IDs to console.

    def send(self,status,value,kind='application/json'):
        body=json.dumps(value,allow_nan=False).encode() if kind=='application/json' else value if isinstance(value,bytes) else value.encode()
        self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)

    def route(self,method):
        path=urlsplit(self.path).path; query=parse_qs(urlsplit(self.path).query)
        store=self.server.store
        if method=='GET':
            if path=='/api/tasks':return self.send(200,[{**get_task(t).describe(),'protocols':get_task(t).PROTOCOLS} for t in available_tasks()])
            if path=='/api/health':
                config=language_configuration()
                return self.send(200,{'status':'ok','local_only':True,
                    'language':config['provider']+'-'+config['mode'] if config['provider'] in {'ollama','openai'} else 'reviewed-template',
                    'response_interpretation':config['interpret_responses'],'language_status':'configuration-only'})
            if path=='/api/sessions':return self.send(200,store.list(query.get('participant',[None])[0]))
            if path.startswith('/api/sessions/'):
                bits=path.strip('/').split('/');sid=bits[2];action=bits[3] if len(bits)>3 else ''
                if action=='knowledge.ttl':return self.send(200,turtle(store.get(sid)),'text/turtle')
                if action=='validation':return self.send(200,shacl_report(store.get(sid)))
                if action=='replay':return self.send(200,store.replay(sid))
                if action in {'','export'}:return self.send(200,store.export(sid))
                return self.send(404,{'error':'Unknown endpoint'})
            files={'/':'index.html','/index.html':'index.html','/teammate.js':'teammate.js','/teammate.css':'teammate.css','/base.css':'base.css','/inspector.html':'inspector.html','/inspector.js':'inspector.js','/slot.png':'slot.png'}
            if path in files:
                f=STATIC/files[path];kind={'.html':'text/html','.js':'text/javascript','.css':'text/css','.png':'image/png'}[f.suffix]
                return self.send(200,f.read_bytes(),kind)
            return self.send(404,{'error':'Not found'})
        # Same-origin local mutations; arbitrary web pages cannot create sessions.
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''):return self.send(403,{'error':'Cross-origin request rejected'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'Use application/json'})
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=200000:return self.send(413,{'error':'Invalid body size'})
        data=json.loads(self.rfile.read(length),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        if path=='/api/sessions':
            s=store.create(data);return self.send(201,{k:s[k] for k in ['id','condition','policy','total_trials','phase','configuration_digest']})
        if path.startswith('/api/sessions/'):
            bits=path.strip('/').split('/');sid=bits[2];action=bits[3] if len(bits)>3 else ''
            if action=='events':
                start=time.perf_counter();record=store.event(sid,data)
                return self.send(200,{'record':record,'processing_ms':round((time.perf_counter()-start)*1000,3)})
            if action=='finish':
                s=store.finish(sid,data);return self.send(200,{'id':s['id'],'completed':s['completed'],'profile':s['profile']})
        return self.send(404,{'error':'Unknown endpoint'})

    def handle_request(self,method):
        try:self.route(method)
        except KeyError as error:self.send(404,{'error':str(error)})
        except (ValidationError,ValueError,TypeError) as error:self.send(422,{'error':str(error)})
        except Exception:
            self.send(500,{'error':'Internal server error; session update was not committed.'})
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')


def make_server(port=8765,data_dir=None):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.store=Store(Path(data_dir or ROOT/'data')/'sessions.sqlite3')
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765);parser.add_argument('--data-dir')
    args=parser.parse_args();server=make_server(args.port,args.data_dir)
    print(f'Socratic prototype: http://127.0.0.1:{server.server_port}\nResearcher inspector: http://127.0.0.1:{server.server_port}/inspector.html',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
