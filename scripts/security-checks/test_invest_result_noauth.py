import urllib.request, urllib.error
req=urllib.request.Request('http://127.0.0.1:8000/api/v1/investigation/4077b803-26c1-4bbc-9cfa-88a47fc347c3/result')
try:
    resp=urllib.request.urlopen(req)
    print('code', resp.status)
except urllib.error.HTTPError as e:
    print('code', e.code)
