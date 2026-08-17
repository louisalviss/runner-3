from pathlib import Path
import re

src=Path('scripts/m88_saba_outright_v6.py').read_text()

open_fn=r'''def open_drawer(frame):
    def state():
        try:return frame.evaluate("""() => {const m=document.querySelector('.main-container'),s=document.querySelector('.side-nav');return {open:m?.getAttribute('data-open-left-menu'),x:s?.getBoundingClientRect().x??null}}""")
        except:return {'open':None,'x':None}
    def ok():
        s=state();return s.get('open')=='true' or (s.get('x') is not None and float(s['x'])>-80)
    res['drawer_x_before']=drawer_x(frame);res['drawer_state_before']=state();attempts=[]
    try:
        e=frame.locator('.header__menu').first
        box=e.evaluate("e=>{let r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}")
        res['header_menu_dom_box']=box
        def check(name):
            frame.page.wait_for_timeout(800);s=state();good=ok();attempts.append({'strategy':name,'ok':good,'state':s})
            if good:res['drawer_open_strategy']=name
            return good
        actions=[
          ('tap',lambda:e.tap(force=True,timeout=5000)),
          ('dom-click',lambda:e.evaluate('e=>e.click()')),
          ('pointer',lambda:(e.dispatch_event('pointerdown',{'pointerType':'touch','isPrimary':True}),e.dispatch_event('pointerup',{'pointerType':'touch','isPrimary':True}),e.dispatch_event('click'))),
          ('react',lambda:e.evaluate("e=>{for(let n=e;n;n=n.parentElement){let k=Object.keys(n).find(x=>x.startsWith('__reactProps$'));if(!k)continue;let p=n[k]||{};for(let z of ['onClick','onTouchEnd','onPointerUp'])if(typeof p[z]=='function'){p[z]({currentTarget:n,target:e,preventDefault(){},stopPropagation(){},nativeEvent:{}});return z}}return null}")),
          ('body-tap',lambda:frame.locator('body').tap(position={'x':box['x']+box['w']/2,'y':box['y']+box['h']/2},force=True,timeout=5000)),
        ]
        for name,fn in actions:
            try:
                r=fn()
                if name=='react':res['drawer_react_handler']=r
                if check(name):break
            except Exception as ex:attempts.append({'strategy':name,'error':type(ex).__name__})
    except Exception as ex:attempts.append({'strategy':'locate','error':type(ex).__name__})
    res['drawer_attempts']=attempts;res['drawer_x_after']=drawer_x(frame);res['drawer_state_after']=state();return ok()
'''

sports_fn=r'''def click_drawer_sports(frame):
    def st():
        try:return frame.evaluate("""() => [...document.querySelectorAll('.side-nav .live-switch__btn')].map(e=>({text:(e.innerText||'').trim(),selected:e.getAttribute('data-selected'),r:(()=>{let r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()}))""")
        except:return []
    def ok():return any(re.fullmatch(r'\s*Sports\s*',x.get('text',''),re.I) and x.get('selected')=='true' for x in st())
    res['drawer_switch_before']=st();attempts=[]
    try:
        e=frame.locator('.side-nav .live-switch__btn').filter(has_text=re.compile(r'^\s*Sports\s*$',re.I)).first
        box=e.evaluate("e=>{let r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}")
        def check(name):
            frame.page.wait_for_timeout(1000);s=st();good=ok();attempts.append({'strategy':name,'ok':good,'state':s})
            if good:res['drawer_sports_strategy']=name
            return good
        actions=[
          ('tap',lambda:e.tap(force=True,timeout=5000)),
          ('text-tap',lambda:e.locator('.live-switch__text').first.tap(force=True,timeout=5000)),
          ('dom-click',lambda:e.evaluate('e=>e.click()')),
          ('pointer',lambda:(e.dispatch_event('pointerdown',{'pointerType':'touch','isPrimary':True}),e.dispatch_event('pointerup',{'pointerType':'touch','isPrimary':True}),e.dispatch_event('click'))),
          ('react',lambda:e.evaluate("e=>{for(let n=e;n;n=n.parentElement){let k=Object.keys(n).find(x=>x.startsWith('__reactProps$'));if(!k)continue;let p=n[k]||{};for(let z of ['onClick','onTouchEnd','onPointerUp'])if(typeof p[z]=='function'){p[z]({currentTarget:n,target:e,preventDefault(){},stopPropagation(){},nativeEvent:{}});return z}}return null}")),
          ('body-tap',lambda:frame.locator('body').tap(position={'x':box['x']+box['w']/2,'y':box['y']+box['h']/2},force=True,timeout=5000)),
        ]
        for name,fn in actions:
            try:
                r=fn()
                if name=='react':res['drawer_sports_react_handler']=r
                if check(name):res['drawer_sports_clicked']=True;break
            except Exception as ex:attempts.append({'strategy':name,'error':type(ex).__name__})
    except Exception as ex:res['drawer_sports_error']=type(ex).__name__
    res['drawer_sports_attempts']=attempts;res['drawer_switch_after']=st();res['drawer_sports_clicked']=ok();return res['drawer_sports_clicked']
'''

more_fn=r'''def click_more(frame):
    def snapshot():
        try:
            return {'drawer':frame.locator('.side-nav').inner_text(timeout=4000)[:1000000],'body':frame.locator('body').inner_text(timeout=4000)[:1500000]}
        except Exception:return {'drawer':'','body':''}
    before=snapshot();res['more_before_text']=before['drawer'];attempts=[]
    try:
        e=frame.locator('.side-nav .side-menu__more').first
        res['more_box_before']=e.bounding_box()
        def check(name):
            frame.page.wait_for_timeout(1200);s=snapshot();has=bool(re.search(r'\bOutright\b',s['body'],re.I));changed=s['drawer']!=before['drawer'];attempts.append({'strategy':name,'has_out_right':has,'changed':changed,'drawer':s['drawer'][:120000]})
            if has:res['more_strategy']=name
            return has
        actions=[
          ('normal-click',lambda:e.click(force=True,timeout=5000)),
          ('dom-click',lambda:e.evaluate('e=>e.click()')),
          ('pointer',lambda:(e.dispatch_event('pointerdown',{'pointerType':'touch','isPrimary':True}),e.dispatch_event('pointerup',{'pointerType':'touch','isPrimary':True}),e.dispatch_event('click'))),
          ('react',lambda:e.evaluate("e=>{for(let n=e;n;n=n.parentElement){let k=Object.keys(n).find(x=>x.startsWith('__reactProps$'));if(!k)continue;let p=n[k]||{};for(let z of ['onClick','onTouchEnd','onPointerUp'])if(typeof p[z]=='function'){p[z]({currentTarget:n,target:e,preventDefault(){},stopPropagation(){},nativeEvent:{}});return z}}return null}")),
        ]
        for name,fn in actions:
            try:
                r=fn()
                if name=='react':res['more_react_handler']=r
                if check(name):res['more_clicked']=True;break
            except Exception as ex:attempts.append({'strategy':name,'error':type(ex).__name__})
    except Exception as ex:attempts.append({'strategy':'locate-more','error':type(ex).__name__})
    res['more_attempts']=attempts;after=snapshot();res['more_after_text']=after['drawer'];res['more_clicked']=bool(re.search(r'\bOutright\b',after['body'],re.I));return res['more_clicked']
'''

for name,repl,next_name in [('open_drawer',open_fn,'drawer_switch_state'),('click_drawer_sports',sports_fn,'click_more'),('click_more',more_fn,'collect_menu_items')]:
    a=src.index(f'def {name}(frame):');b=src.index(f'\ndef {next_name}(frame):',a);src=src[:a]+repl+src[b:]
exec(compile(src,'m88_v8_runtime.py','exec'),{'__name__':'__main__','__file__':'m88_v8_runtime.py'})
