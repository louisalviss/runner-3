from pathlib import Path
import re

src = Path('scripts/m88_saba_outright_v6.py').read_text()
replacement = r'''def click_drawer_sports(frame):
    def state():
        try:
            return frame.evaluate(r"""() => Array.from(document.querySelectorAll('.side-nav .live-switch__btn')).map(e=>{let r=e.getBoundingClientRect();return {text:(e.innerText||'').trim(),selected:e.getAttribute('data-selected'),rect:{x:r.x,y:r.y,w:r.width,h:r.height},html:e.outerHTML.slice(0,800)}})""")
        except Exception:
            return []

    def selected():
        for x in state():
            if re.fullmatch(r'\s*Sports\s*', x.get('text',''), re.I):
                return x.get('selected') == 'true'
        return False

    res['drawer_switch_before'] = state()
    try:
        loc = frame.locator('.side-nav .live-switch__btn').filter(has_text=re.compile(r'^\s*Sports\s*$', re.I)).first
        if loc.count() == 0:
            res['drawer_sports_clicked'] = False
            res['drawer_sports_error'] = 'Sports locator missing'
            return False
        info = loc.evaluate("e=>{let r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,html:e.outerHTML.slice(0,1000)}}")
        res['drawer_sports_rect'] = info
        attempts = []

        def check(name):
            frame.page.wait_for_timeout(1200)
            st = state()
            ok = selected()
            attempts.append({'strategy':name,'selected':ok,'state':st})
            return ok

        try:
            loc.tap(force=True, timeout=5000)
            if check('locator.tap(force)'):
                res['drawer_sports_clicked']=True; res['drawer_sports_strategy']='locator.tap(force)'; res['drawer_switch_after']=state(); return True
        except Exception as e:
            attempts.append({'strategy':'locator.tap(force)','error':type(e).__name__})

        try:
            child = loc.locator('.live-switch__text').first
            child.tap(force=True, timeout=5000)
            if check('text.tap(force)'):
                res['drawer_sports_clicked']=True; res['drawer_sports_strategy']='text.tap(force)'; res['drawer_switch_after']=state(); return True
        except Exception as e:
            attempts.append({'strategy':'text.tap(force)','error':type(e).__name__})

        try:
            loc.evaluate('e=>e.click()')
            if check('element.click()'):
                res['drawer_sports_clicked']=True; res['drawer_sports_strategy']='element.click()'; res['drawer_switch_after']=state(); return True
        except Exception as e:
            attempts.append({'strategy':'element.click()','error':type(e).__name__})

        try:
            loc.dispatch_event('pointerdown', {'pointerType':'touch','isPrimary':True,'button':0,'buttons':1})
            loc.dispatch_event('pointerup', {'pointerType':'touch','isPrimary':True,'button':0,'buttons':0})
            loc.dispatch_event('click', {'button':0})
            if check('pointerdown/up/click'):
                res['drawer_sports_clicked']=True; res['drawer_sports_strategy']='pointerdown/up/click'; res['drawer_switch_after']=state(); return True
        except Exception as e:
            attempts.append({'strategy':'pointerdown/up/click','error':type(e).__name__})

        try:
            cx = float(info['x']) + float(info['w'])/2
            cy = float(info['y']) + float(info['h'])/2
            frame.locator('body').tap(position={'x':cx,'y':cy}, force=True, timeout=5000)
            if check('body.tap(center)'):
                res['drawer_sports_clicked']=True; res['drawer_sports_strategy']='body.tap(center)'; res['drawer_switch_after']=state(); return True
        except Exception as e:
            attempts.append({'strategy':'body.tap(center)','error':type(e).__name__})

        try:
            cx = float(info['x']) + float(info['w'])/2
            cy = float(info['y']) + float(info['h'])/2
            frame.locator('body').click(position={'x':cx,'y':cy}, force=True, timeout=5000)
            if check('body.click(center)'):
                res['drawer_sports_clicked']=True; res['drawer_sports_strategy']='body.click(center)'; res['drawer_switch_after']=state(); return True
        except Exception as e:
            attempts.append({'strategy':'body.click(center)','error':type(e).__name__})

        res['drawer_sports_attempts'] = attempts
        res['drawer_switch_after'] = state()
        res['drawer_sports_clicked'] = False
        return False
    except Exception as e:
        res['drawer_sports_clicked'] = False
        res['drawer_sports_error'] = type(e).__name__
        return False
'''
start = src.index('def click_drawer_sports(frame):')
end = src.index('\ndef click_more(frame):', start)
new = src[:start] + replacement + src[end:]
exec(compile(new, 'm88_saba_outright_v7_runtime.py', 'exec'), {'__name__':'__main__','__file__':'m88_saba_outright_v7_runtime.py'})
