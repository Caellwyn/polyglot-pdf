import os
import traceback
from google import genai

def mask(s):
    if not s:
        return None
    return f"<REDACTED len={len(s)}>"

vars_to_check = ['GOOGLE_API_KEY','GEMINI_API_KEY','GOOGLE_CLOUD_PROJECT','GOOGLE_CLOUD_LOCATION','PROJECT','LOCATION','GOOGLE_APPLICATION_CREDENTIALS']
for v in vars_to_check:
    val = os.environ.get(v)
    if val:
        if 'KEY' in v or 'CREDENTIALS' in v:
            print(f"{v}=SET (len={len(val)})")
        else:
            print(f"{v}={val}")
    else:
        print(f"{v}=NOT SET")

print('\nCreating genai.Client() (will not make network calls)')
try:
    ClientCls = getattr(genai, 'Client', None)
    if ClientCls is None:
        print('genai.Client not available')
    else:
        API_KEY = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
        client = ClientCls(api_key=API_KEY) if API_KEY else ClientCls()
        api_client = getattr(client, '_api_client', None)
        if api_client is None:
            print('no _api_client attribute on client')
        else:
            try:
                base_url = getattr(api_client, '_http_options', None)
                if base_url is not None and getattr(base_url, 'base_url', None):
                    print('http_options.base_url =', base_url.base_url)
                else:
                    print('http_options.base_url = <not set>')
            except Exception:
                print('http_options.base_url = <error>')
            try:
                loc = getattr(api_client, 'location', None)
                proj = getattr(api_client, 'project', None)
                print('location=', loc, 'project=', proj)
            except Exception:
                print('could not read location/project')
            try:
                if hasattr(api_client, '_websocket_base_url'):
                    wb = api_client._websocket_base_url()
                    print('_websocket_base_url() ->', wb)
                else:
                    print('_websocket_base_url() not available')
            except Exception as e:
                print('_websocket_base_url() raised:', type(e), e)
except Exception as e:
    print('client construction/inspection failed:', type(e), e)
    traceback.print_exc()
