from pathlib import Path
# V8 reload after nested React handler fix
code = Path('scripts/m88_saba_outright_v8.py').read_text()
exec(compile(code, 'm88_saba_outright_v8.py', 'exec'), {'__name__':'__main__','__file__':'m88_saba_outright_v8.py'})
