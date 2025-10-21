import socket

hosts = [
    'api.generativeai.googleapis.com',
    'generativeai.googleapis.com',
    'www.google.com',
]

for h in hosts:
    try:
        infos = socket.getaddrinfo(h, 443)
        print(f'{h}: OK ({len(infos)} records)')
    except Exception as e:
        print(f'{h}: FAIL ({e})')
