import urllib.request, urllib.error
req=urllib.request.Request('http://127.0.0.1:8000/api/v1/cases?page=1')
try:
    resp=urllib.request.urlopen(req)
    print('code', resp.status)
    print('accessible')
except urllib.error.HTTPError as e:
    print('code', e.code)
