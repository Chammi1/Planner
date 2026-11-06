import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode
from app.security import validate_init_data
from app.validation import validate_state, InvalidState

TOKEN='123456:test-token'
OWNER=1234567
NOW=1800000000

def init_data(user=OWNER, date=NOW):
    data={'auth_date':str(date),'user':json.dumps({'id':user},separators=(',',':')),'query_id':'test'}
    check='\n'.join(f'{key}={value}' for key,value in sorted(data.items()))
    secret=hmac.new(b'WebAppData',TOKEN.encode(),hashlib.sha256).digest()
    data['hash']=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
    return urlencode(data)

def document():
    return {'tasks':[{'id':'a','title':'Зарядка','order':0},{'id':'b','title':'Душ','order':1}], 'entries':{'a':{'2026-11-06':'done'},'b':{'2026-11-06':'planned'}}, 'times':{'a':{'2026-11-06':{'start':'07:00','end':'07:20'}},'b':{'2026-11-06':{'type':'after','taskId':'a','offset':0,'duration':15}}},'settings':{'wake':'07:00','sleep':'23:00'}}

class SecurityTests(unittest.TestCase):
    def test_signed_owner(self):
        self.assertEqual(validate_init_data(init_data(),TOKEN,OWNER,now=NOW),OWNER)
    def test_tamper(self):
        with self.assertRaises(ValueError): validate_init_data(init_data().replace('test','evil'),TOKEN,OWNER,now=NOW)
    def test_other_user(self):
        with self.assertRaises(PermissionError): validate_init_data(init_data(user=8),TOKEN,OWNER,now=NOW)
    def test_expired(self):
        with self.assertRaises(ValueError): validate_init_data(init_data(date=NOW-3601),TOKEN,OWNER,now=NOW)
    def test_future(self):
        with self.assertRaises(ValueError): validate_init_data(init_data(date=NOW+31),TOKEN,OWNER,now=NOW)
    def test_duplicates(self):
        with self.assertRaises(ValueError): validate_init_data(init_data()+'&auth_date=1',TOKEN,OWNER,now=NOW)

class StateTests(unittest.TestCase):
    def test_legacy_and_relative(self):
        self.assertEqual(validate_state(document())['times']['a']['2026-11-06']['end'],'07:20')
    def test_invalid_status(self):
        data=document(); data['entries']['a']['2026-11-06']='bad'
        with self.assertRaises(InvalidState): validate_state(data)
    def test_cycle(self):
        data=document(); data['times']['a']['2026-11-06']={'type':'after','taskId':'b','offset':0,'duration':20}
        with self.assertRaises(InvalidState): validate_state(data)
    def test_missing_source_is_warning_not_loss(self):
        data=document(); data['times']['b']['2026-11-06']['taskId']='removed'
        validate_state(data)
    def test_invalid_time(self):
        data=document(); data['times']['a']['2026-11-06']['end']='25:00'
        with self.assertRaises(InvalidState): validate_state(data)
    def test_bad_settings(self):
        data=document(); data['settings']['sleep']='06:00'
        with self.assertRaises(InvalidState): validate_state(data)
    def test_unknown_task(self):
        data=document(); data['entries']['unknown']={}
        with self.assertRaises(InvalidState): validate_state(data)
    def test_reserved_id(self):
        data=document(); data['tasks'][0]['id']='__proto__'
        with self.assertRaises(InvalidState): validate_state(data)

if __name__=='__main__': unittest.main()
