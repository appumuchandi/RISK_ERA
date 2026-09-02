import urllib.request
req=urllib.request.Request('http://127.0.0.1:8000/api/v1/cases?page=1')
try:
    urllib.request.urlopen(req)
    print('unexpected success')
except urllib.error.HTTPError as e:
    print(e.code)
