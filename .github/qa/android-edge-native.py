import json, subprocess as sp, time, urllib.request as u, threading, re, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.etree import ElementTree
from PIL import Image
out=Path('/tmp/android-proof');out.mkdir(exist_ok=True)
def adb(*args):
    return sp.check_output(['adb',*args],stderr=sp.DEVNULL)
def fetch(port,path,method='GET',data=None):
    return u.urlopen(u.Request(f'http://127.0.0.1:{port}'+path,data=data,method=method,headers={'Content-Type':'application/json'}),timeout=10)
gate={}
class Capture(BaseHTTPRequestHandler):
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        key=(data['variant'],data['phase'])
        print('native browser event',key,data,flush=True)
        gate[key]=data
        end=time.monotonic()+65
        while key in gate and time.monotonic()<end:time.sleep(.15)
        self.send_response(200);self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(b'ok')
threading.Thread(target=ThreadingHTTPServer(('127.0.0.1',8224),Capture).serve_forever,daemon=True).start()
adb('reverse','tcp:8224','tcp:8224')
js="""<script>
localStorage.setItem('selection', JSON.stringify(SELECTION));
(async function(){
const delay=ms=>new Promise(r=>setTimeout(r,ms)),phase=async (name,props={})=>fetch('http://127.0.0.1:8224/snapshot',{method:'POST',headers:{'Content-Type':'text/plain'},body:JSON.stringify({variant:'VARIANT',phase:name,ua:navigator.userAgent,...props})});
const wait=async fn=>{for(let i=0;i<400;i++){if(fn())return fn();await delay(150)}throw new Error('Timeout '+fn)};
try{
await wait(()=>document.querySelector('.choices button'));
(await wait(()=>document.querySelector('[data-mobile-menu-trigger]'))).click();
const menu=await wait(()=>document.querySelector('.mobile-game-menu'));
await document.fonts.ready;
const scroll=menu.querySelector('.mobile-menu-scroll');
for (const pos of ['top','bottom']){
 if(pos==='bottom'){scroll.scrollTop=scroll.scrollHeight;await wait(()=>scroll.scrollTop+scroll.clientHeight>=scroll.scrollHeight-1)}
 await delay(1200);
 const r=menu.getBoundingClientRect(),s=getComputedStyle(menu);
 await phase(pos,{rect:[r.x,r.y,r.width,r.height],viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,edges:['Top','Right','Bottom','Left'].map(k=>s['border'+k+'Width']),borderColor:s.borderColor,bg:s.backgroundColor,inner:getComputedStyle(menu.querySelector('.menu-world')).borderWidth});
}
menu.querySelector('.mobile-menu-tools button:nth-child(2)').click();
await wait(()=>document.querySelector('.settings-dialog'));
await phase('settings');
}catch(e){await phase('error',{message:String(e),page:document.body.innerText.slice(0,200)})}
})()
</script>"""
for version,port,build in [('before',8216,Path('/tmp/pre-edge/frontend/dist')),('after',8217,Path.cwd()/'frontend/dist')]:
    sel=json.load(fetch(port,'/test/phone-seed?incoming=false','POST'))
    fetch(port,'/api/worlds/'+str(sel['world'])+'/presentation','PUT',b'{"theme_id":"graphite"}').read()
    index=build/'index.html'
    original=index.read_text()
    index.write_text(original.replace('<head>','<head>'+js.replace('SELECTION',json.dumps(sel)).replace('VARIANT',version),1))
    try:
        adb('shell','am','force-stop','org.mozilla.firefox')
        adb('shell','am','start','-a','android.intent.action.VIEW','-d',f'http://127.0.0.1:{port}/?android-edge={version}','-p','org.mozilla.firefox')
        for phase in ['top','bottom','settings']:
            key=(version,phase);end=time.monotonic()+105
            while key not in gate and time.monotonic()<end:
                if (version,'error') in gate:raise RuntimeError(gate[(version,'error')])
                time.sleep(.25)
            if key not in gate:raise RuntimeError('No Android events for '+str(key))
            info=gate[key]
            if phase!='settings':
                assert 'Android' in info['ua'] and 'Firefox' in info['ua'] and info['edges']==(['0px']*4 if version=='after' else ['1px']*4) and info['inner']=='1px'
                assert abs(info['rect'][0])+abs(info['rect'][1])<1 and max(abs(a-b) for a,b in zip(info['rect'][2:],info['viewport']))<1
                shot=out/f'{version}-{phase}-device.png';shot.write_bytes(adb('exec-out','screencap','-p'))
                adb('shell','uiautomator','dump','/sdcard/edge-window.xml')
                tree=ElementTree.fromstring(adb('exec-out','cat','/sdcard/edge-window.xml'))
                image=Image.open(shot)
                w,h=info['viewport'];scale=image.width/w
                nodes=[]
                for node in tree.iter('node'):
                    bounds=tuple(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
                    if len(bounds)!=4:continue
                    x,y,ex,ey=bounds
                    score=abs(ex-x-round(w*scale))+abs(ey-y-round(h*scale))
                    nodes.append((score, bounds, node.get('class'),node.get('resource-id')))
                nodes.sort()
                print('Android content bounds',nodes[:4],flush=True)
                best=nodes[0]
                if best[0]>4:
                    # The menu brand spans the viewport. Its first row is the first row of the uniform web background (or the pre-fix border).
                    pixel=tuple(map(int,re.findall(r'\d+',info['bg'] if version=='after' else info['borderColor'])[:3]))
                    im=image.convert('RGB')
                    yy=next(y for y in range(im.height) if all(im.getpixel((x,y))==pixel for x in (0,1,3,im.width-1)))
                    box=(0,yy,im.width,yy+round(h*scale))
                else:box=best[1]
                print('PNG web bounds',box,flush=True)
                image.crop(box).save(out/f'{version}-{phase}-web.png')
                (out/f'{version}-{phase}.json').write_text(json.dumps(info))
            del gate[key]
    finally:index.write_text(original)
(out/'browser').write_text('Firefox')
