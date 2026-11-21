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
                assert 'Android' in info['ua'] and 'Firefox' in info['ua']
                physical=lambda width:round(float(width.removesuffix('px'))*info['dpr'])
                assert list(map(physical,info['edges']))==([0]*4 if version=='after' else [1]*4) and physical(info['inner'])==1
                assert abs(info['rect'][0])+abs(info['rect'][1])<1 and max(abs(a-b) for a,b in zip(info['rect'][2:],info['viewport']))<1
                def ui():
                    adb('shell','uiautomator','dump','/sdcard/edge-window.xml')
                    return ElementTree.fromstring(adb('exec-out','cat','/sdcard/edge-window.xml'))
                tree=ui()
                for _ in range(3):
                    candidates=[n for n in tree.iter('node') if (n.get('text','').lower() in {'got it','not now','no thanks','dismiss','skip','skip introduction','continue without account','ok','maybe later'} and n.get('package') in {'org.mozilla.firefox','com.android.permissioncontroller'})]
                    if not candidates:break
                    x,y,ex,ey=map(int,re.findall(r'-?\d+',candidates[0].get('bounds')))
                    adb('shell','input','tap',str((x+ex)//2),str((y+ey)//2));time.sleep(.8);tree=ui()
                print('Android UI',[(n.get('resource-id',''),(n.get('text') or n.get('content-desc',''))[:65]) for n in tree.iter('node') if n.get('text') or n.get('content-desc')][:60],flush=True)
                shot=out/f'{version}-{phase}-device.png';shot.write_bytes(adb('exec-out','screencap','-p'))
                im=Image.open(shot).convert('RGB')
                frame=next((n for n in tree.iter('node') if n.get('resource-id','').endswith(':id/engineView')),None)
                if frame is None:
                    # The first run establishes the browser content rectangle, which is stable across this fixture.
                    assert 'last_box' in globals(), 'Missing Android browser bounds'
                    box=last_box
                else:box=tuple(map(int,re.findall(r'-?\d+',frame.get('bounds'))))
                last_box=box
                web=im.crop(box)
                from collections import Counter
                columns=[[(x,y) for x in range(web.width)] for y in (0,web.height-1)]
                columns += [[(x,y) for y in range(web.height)] for x in (0,web.width-1)]
                print('Physical edge samples',version,phase,box,[Counter(web.getpixel(pos) for pos in line).most_common(2) for line in columns],flush=True)
                web.save(out/f'{version}-{phase}-web.png')
                (out/f'{version}-{phase}.json').write_text(json.dumps(info))
            del gate[key]
    finally:index.write_text(original)
(out/'browser').write_text('Firefox')
