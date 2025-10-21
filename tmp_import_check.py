import sys
try:
    import backend.main as appmod
    print('OK')
except Exception as e:
    print('IMPORT ERROR', type(e).__name__, e)
    sys.exit(1)
