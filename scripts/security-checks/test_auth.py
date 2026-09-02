import urllib.request, json
data=json.dumps({'username':'bad','password':'bad'}).encode()
req=urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login', data=data, headers={'Content-Type':'application/json'})
try:
    urllib.request.urlopen(req)
    print('unexpected success')
except urllib.error.HTTPError as e:
    print(e.code)
