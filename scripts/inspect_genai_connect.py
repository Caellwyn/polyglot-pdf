import os
import json
import traceback

from google import genai

MODEL = os.environ.get('GENAI_MODEL', 'gemini-2.5-flash-preview')
API_KEY = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')

print('Using API key from env? ', 'yes' if API_KEY else 'no')

try:
    ClientCls = getattr(genai, 'Client', None)
    if ClientCls is None:
        print('genai.Client not found on imported module')
    else:
        try:
            client = ClientCls(api_key=API_KEY) if API_KEY else ClientCls()
            print('Client created:', client)
            try:
                connect_obj = client.aio.live.connect(model=MODEL, config={"response_modalities": ["AUDIO"]})
                print('connect_obj repr:', repr(connect_obj)[:1000])
                for attr in ('url','uri','_url','endpoint'):
                    try:
                        v = getattr(connect_obj, attr, None)
                        if v is not None:
                            print(f'connect_obj.{attr} =', v)
                    except Exception:
                        pass
            except Exception as e:
                print('failed creating connect_obj:', type(e), e)
                traceback.print_exc()
        except Exception as e:
            print('Client construction failed:', type(e), e)
            traceback.print_exc()
except Exception as e:
    print('Unexpected import error:', type(e), e)
    traceback.print_exc()
