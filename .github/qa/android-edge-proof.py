from pathlib import Path
from urllib.request import Request,urlopen
import json,subprocess
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

out=Path('/tmp/android-proof')
opts=webdriver.FirefoxOptions()
opts.set_capability('moz:firefoxOptions',{'androidPackage':'org.mozilla.firefox'})
opts.enable_mobile(android_package='org.mozilla.firefox')
opts.set_preference('browser.aboutwelcome.enabled',False)
opts.set_preference('browser.shell.checkDefaultBrowser',False)
driver=webdriver.Firefox(options=opts,service=Service(log_output='/tmp/geckodriver.log'))
try:
 wait=WebDriverWait(driver,40)
 for label,port in [('before',8216),('after',8217)]:
  origin='http://127.0.0.1:'+str(port)
  selected=json.load(urlopen(Request(origin+'/test/phone-seed?incoming=false',method='POST')))
  urlopen(Request(origin+'/api/worlds/'+str(selected['world'])+'/presentation',method='PUT',headers={'Content-Type':'application/json'},data=b'{"theme_id":"graphite"}')).read()
  driver.get(origin)
  driver.execute_script("localStorage.setItem('selection',JSON.stringify(arguments[0]));",selected)
  driver.refresh()
  wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,'.choices button')))
  wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,'[data-mobile-menu-trigger]'))).click()
  menu=wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,'.mobile-game-menu')))
  driver.execute_async_script("const cb=arguments[0];document.fonts.ready.then(()=>Promise.allSettled(document.getAnimations().filter(a=>Number.isFinite(a.effect?.getComputedTiming().endTime)).map(a=>a.finished))).then(()=>cb('ready'))")
  for state in ('top','bottom'):
   if state=='bottom':
    for _ in range(5):
     w,h=driver.execute_script('return [innerWidth,innerHeight]')
     cmd={'actions':[{'type':'pointer','id':'finger','parameters':{'pointerType':'touch'},'actions':[{'type':'pointerMove','duration':0,'x':w//2,'y':int(h*.83)},{'type':'pointerDown','button':0},{'type':'pointerMove','duration':400,'x':w//2,'y':int(h*.25)},{'type':'pointerUp','button':0}]}]}
     driver.execute('actions',cmd)
     if driver.execute_script("const e=document.querySelector('.mobile-menu-scroll');return e.scrollTop+e.clientHeight>=e.scrollHeight-1"):break
    wait.until(lambda d:d.execute_script("const e=document.querySelector('.mobile-menu-scroll');return e.scrollTop+e.clientHeight>=e.scrollHeight-1"))
   info=driver.execute_script("const e=arguments[0],r=e.getBoundingClientRect(),s=getComputedStyle(e);return {ua:navigator.userAgent,viewport:[innerWidth,innerHeight],rect:[r.x,r.y,r.width,r.height],edges:['Top','Right','Bottom','Left'].map(k=>s['border'+k+'Width']),inner:getComputedStyle(e.querySelector('.menu-world')).borderTopWidth,bg:s.backgroundColor}",menu)
   print(label,state,info,flush=True)
   assert 'Android' in info['ua'] and 'Firefox' in info['ua']
   assert info['edges']==(['0px']*4 if label=='after' else ['1px']*4)
   assert info['inner']=='1px' and info['rect'][:2]==[0,0]
   assert all(abs(a-b)<1 for a,b in zip(info['rect'][2:],info['viewport']))
   (out/(label+'-'+state+'.json')).write_text(json.dumps(info))
   (out/(label+'-'+state+'-web.png')).write_bytes(driver.get_screenshot_as_png())
   (out/(label+'-'+state+'-device.png')).write_bytes(subprocess.check_output(['adb','exec-out','screencap','-p']))
  menu.find_element(By.XPATH,'.//button[normalize-space()="Настройки"]').click()
  wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR,'.settings-dialog')))
finally:
 driver.quit()
