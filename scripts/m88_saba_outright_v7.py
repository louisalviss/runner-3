from pathlib import Path
# V8 reload after state-aware More handler
code = Path('scripts/m88_saba_outright_v8.py').read_text()
exec(compile(code, 'm88_saba_outright_v8.py', 'exec'), {'__name__':'__main__','__file__':'m88_saba_outright_v8.py'})
