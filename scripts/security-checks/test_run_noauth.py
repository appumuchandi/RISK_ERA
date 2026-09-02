import urllib.request, urllib.error, urllib.parse
case_id='4077b803-26c1-4bbc-9cfa-88a47fc347c3'
url='http://127.0.0.1:8000/api/v1/investigation/'+case_id+'/run?authorization=Bearer%20invalid'
req=urllib.request.Request(url, data=b'', method='POST')
try:
    resp=urllib.request.urlopen(req)
    print('code', resp.status)
    print(resp.read().decode()[:200])
except urllib.error.HTTPError as e:
    print('code', e.code)
