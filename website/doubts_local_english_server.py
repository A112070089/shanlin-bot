"""Loopback-only Kokoro service. No transcript or audio logging/storage."""
import io,json,re,threading,time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MODEL_ID='mlx-community/Kokoro-82M-bf16'
model=None
lock=threading.Lock()
cache=OrderedDict()

def synthesize(text):
    import numpy as np
    import soundfile as sf
    if text in cache:
        cache.move_to_end(text)
        return cache[text]
    chunks=[];rate=None
    for result in model.generate(text=text,voice='af_heart',speed=1.0,lang_code='a'):
        rate=int(result.sample_rate)
        chunks.append(np.asarray(result.audio,dtype=np.float32).reshape(-1))
    if not chunks:raise ValueError('empty_audio')
    buf=io.BytesIO();sf.write(buf,np.concatenate(chunks),rate,format='WAV',subtype='PCM_16');audio=buf.getvalue()
    if not 44<len(audio)<=8*1024*1024:raise ValueError('audio_size')
    cache[text]=audio
    while len(cache)>64 or sum(map(len,cache.values()))>64*1024*1024:cache.popitem(last=False)
    return audio

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,code,data,kind='application/json'):
        if not isinstance(data,bytes):data=json.dumps(data).encode()
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def allowed(self):
        return self.headers.get('Host') in ('127.0.0.1:8766','localhost:8766') and not self.headers.get('Origin')
    def do_GET(self):
        if not self.allowed():return self.reply(403,{'status':'error'})
        if self.path!='/health':return self.reply(404,{'status':'error'})
        self.reply(200,{'status':'success','service':'doubts-kokoro','build':'7.6','ready':model is not None})
    def do_POST(self):
        self.connection.settimeout(10)
        if not self.allowed():return self.reply(403,{'status':'error'})
        if self.path!='/speak':return self.reply(404,{'status':'error'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096:raise ValueError()
            text=json.loads(self.rfile.read(size)).get('text')
            if not isinstance(text,str) or not 1<=len(text.strip())<=200 or re.search(r'[\u3400-\u9fff]',text):raise ValueError()
            text=text.strip()
        except Exception:return self.reply(422,{'status':'error','error_code':'invalid_text'})
        if not lock.acquire(blocking=False):return self.reply(503,{'status':'error','error_code':'local_voice_busy'})
        try:self.reply(200,synthesize(text),'audio/wav')
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:
            print('語音生成失敗：'+type(exc).__name__,flush=True)
            self.reply(503,{'status':'error','error_code':'local_voice_failed'})
        finally:lock.release()

def main():
    global model
    from mlx_audio.tts.utils import load_model
    print('正在載入 Kokoro 英文模型…',flush=True)
    model=load_model(MODEL_ID)
    synthesize('Hello. Your local English voice is ready.')
    server=ThreadingHTTPServer(('127.0.0.1',8766),Handler);server.daemon_threads=True
    print('READY：本機英文語音已啟動（127.0.0.1:8766）。此視窗請保持開啟。',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
