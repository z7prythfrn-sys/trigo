#!/usr/bin/env python3
"""TRIGO quiz LAN buzzer server. Python standard library only."""
import json, socket, threading, secrets, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('PORT','8765'))
TEACHER_KEY = os.environ.get('TEACHER_KEY') or secrets.token_urlsafe(6)  # secret for the teacher link on a public site
lock=threading.Lock()
TOKEN=secrets.token_hex(16)  # only the teacher page opened via localhost receives it
state={'round':-1,'phase':'intro','holder':None,'blocked':[],'answer_choice':None,'scored':None,'remaining':20,'paused':False,'version':0,'total':12,'question':'','choices':[],'category':'','scores':[0,0,0],'correct_choice':None,'explanation':''}

def statecopy(): return dict(state, blocked=list(state['blocked']))
def localip():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        s.connect(('1.1.1.1',80));return s.getsockname()[0]
    except OSError: return 'КОМПЬЮТЕРДІҢ_IP_АДРЕСІ'
    finally:s.close()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass
    def reply(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)))
        self.end_headers();self.wfile.write(b)
    def do_HEAD(self):
        self.send_response(200);self.end_headers()
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/state':
            with lock: data=statecopy()
            return self.reply(data)
        q=parse_qs(urlparse(self.path).query)
        direct=self.client_address[0] in ('127.0.0.1','::1') and not any(self.headers.get(h) for h in ('X-Forwarded-For','Forwarded','X-Real-IP','CF-Connecting-IP','Via'))
        local=direct or secrets.compare_digest((q.get('key') or [''])[0],TEACHER_KEY)
        if path in ('/','/index.html') and not local:
            self.send_response(302);self.send_header('Location','/team.html');self.end_headers();return
        filename={'/':'index.html','/index.html':'index.html','/team.html':'team.html','/hero_left.png':'hero_left.png','/hero_right.png':'hero_right.png','/intro.jpg':'intro.jpg'}.get(path)
        if filename is None:
            self.send_error(404);return
        b=(ROOT/filename).read_bytes()
        if filename=='index.html':
            ph=b'<!--HOST_TOKEN-->'
            b=b.replace(ph,('<script>window.HOST_TOKEN="%s"</script>'%TOKEN).encode() if local else b'')
        self.send_response(200)
        self.send_header('Content-Type', 'image/png' if filename.endswith('.png') else ('image/jpeg' if filename.endswith('.jpg') else 'text/html; charset=utf-8'))
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)))
        self.end_headers();self.wfile.write(b)
    def do_POST(self):
        try:
            count=min(int(self.headers.get('Content-Length','0')),20480)
            data=json.loads(self.rfile.read(count).decode())
        except (ValueError,UnicodeError):return self.reply({'error':'Bad JSON'},400)
        path=urlparse(self.path).path
        with lock:
            if path=='/api/set':
                if not secrets.compare_digest(self.headers.get('X-Host-Token',''),TOKEN):
                    return self.reply({'error':'host only'},403)
                n=data.get('round'); phase=data.get('phase')
                if not isinstance(n,int) or phase not in ['intro','open','answer','revealed','end']:
                    return self.reply({'error':'bad state'},400)
                # Host is the authority for game phase and blocked teams.
                old_holder=state['holder']; old_round=state['round']
                state['round']=n;state['phase']=phase
                state['blocked']=[int(x) for x in data.get('blocked',[]) if x in [0,1,2]]
                state['holder']=data.get('holder') if phase=='answer' else None
                if phase=='answer' and old_round==n and old_holder==state['holder']:
                    pass # Preserve already submitted phone answer.
                else:
                    state['answer_choice']=None
                sc=data.get('scored'); state['scored']=sc if (phase=='revealed' and sc in [0,1,2]) else None
                state['remaining']=max(0,min(999,int(data.get('remaining',20))))
                state['paused']=bool(data.get('paused',False))
                state['total']=max(1,min(24,int(data.get('total',12))))
                state['question']=str(data.get('question',''))[:1200]
                state['category']=str(data.get('category',''))[:200]
                opts=data.get('choices',[])
                state['choices']=[str(c)[:400] for c in opts[:4]] if isinstance(opts,list) else []
                scs=data.get('scores',[0,0,0])
                state['scores']=[int(v) for v in scs] if isinstance(scs,list) and len(scs)==3 else [0,0,0]
                state['correct_choice']=data.get('correct_choice') if phase=='revealed' and data.get('correct_choice') in [0,1,2,3] else None
                state['explanation']=str(data.get('explanation',''))[:600] if phase=='revealed' else ''
                state['version']+=1
            elif path=='/api/buzz':
                team=data.get('team');n=data.get('round')
                if team not in [0,1,2] or n != state['round']:
                    return self.reply({'error':'bad team/round','state':statecopy()},400)
                if state['phase']=='open' and not state['paused'] and state['holder'] is None and team not in state['blocked']:
                    state['holder']=team;state['phase']='answer';state['answer_choice']=None;state['version']+=1
            elif path=='/api/answer':
                team=data.get('team');choice=data.get('choice')
                if team==state['holder'] and not state['paused'] and state['phase']=='answer' and choice in [0,1,2,3] and state['answer_choice'] is None:
                    state['answer_choice']=choice;state['version']+=1
            else: return self.reply({'error':'not found'},404)
            snap=statecopy()
        return self.reply(snap)

if __name__=='__main__':
    print('\nTRIGO ШАЙҚАСЫ — СЕРВЕР ІСКЕ ҚОСЫЛДЫ',flush=True)
    print(f'Порт: {PORT}',flush=True)
    print(f'МҰҒАЛІМ КІЛТІ: {TEACHER_KEY}  ->  мұғалім сілтемесі: <САЙТ>/?key={TEACHER_KEY}',flush=True)
    print('ТОПТАРҒА ОРТАҚ СІЛТЕМЕ: <САЙТ>/team.html\n',flush=True)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
