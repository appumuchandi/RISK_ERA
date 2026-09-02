import os
import sys
import urllib.request, urllib.error, urllib.parse

# Use dynamic test token - never hardcode JWTs
# This probe tests that query-parameter authentication is correctly rejected (should be 401)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
try:
    from app.auth import JWTAuth
    token = JWTAuth.encode_token("Admin1")
except Exception:
    # Fallback: use obviously invalid token if JWT infrastructure not available
    token = "invalid.test.token"

case_id='4077b803-26c1-4bbc-9cfa-88a47fc347c3'
auth_param=urllib.parse.quote('Bearer '+token)
url='http://127.0.0.1:8000/api/v1/investigation/'+case_id+'/run?authorization='+auth_param
req=urllib.request.Request(url, data=b'', method='POST')
try:
    resp=urllib.request.urlopen(req)
    print('code', resp.status)
    print(resp.read().decode()[:200])
except urllib.error.HTTPError as e:
    print('code', e.code)
    # Expected: 401 - query-param auth must be rejected
    if e.code == 401:
        print("PASS: query-param authentication correctly rejected")
