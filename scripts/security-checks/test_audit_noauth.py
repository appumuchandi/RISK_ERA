import urllib.request, urllib.error
req=urllib.request.Request('http://127.0.0.1:8000/api/v1/audit')
try:
    resp=urllib.request.urlopen(req)
    print('code', resp.status)
except urllib.error.HTTPError as e:
    print('code', e.code)
