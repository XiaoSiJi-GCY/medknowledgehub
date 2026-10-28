"""Real cross-service integration smoke. Prints checks, never credentials or conversation text."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.getenv('CARE_SUITE_ENV_FILE', ROOT / '.env'))


def main():
    config = dotenv_values(CONFIG)
    token = config.get('SERVICE_TOKEN', '')
    checks = {}
    with httpx.Client(base_url='http://127.0.0.1:8000/api/v1/', timeout=150) as care, httpx.Client(
        base_url=config.get('MEDHUB_API_URL', 'http://127.0.0.1:8010/api/v1').rstrip('/')+'/',
        headers={'Authorization': 'Bearer '+token}, timeout=30,
    ) as hub:
        me = hub.get('auth/me'); me.raise_for_status()
        assert me.json()['role'] == 'viewer'
        checks['read_only_service_identity'] = 'passed'
        name = 'integration_'+secrets.token_hex(5)
        password = secrets.token_urlsafe(20)
        registration = care.post('auth/register', json={'username':name,'password':password})
        registration.raise_for_status()
        headers = {'Authorization':'Bearer '+registration.json()['access_token']}
        status = care.get('knowledge/status', headers=headers); status.raise_for_status()
        assert status.json()['backend'] == 'medknowledgehub' and status.json()['status'] == 'ready'
        checks['carepilot_connected_to_hub'] = 'passed'
        initial = care.post('consultations/chat', headers=headers, json={'message':'我咳嗽持续三周了。'})
        initial.raise_for_status(); first = initial.json(); session_id = first['session_id']
        answer = care.post('consultations/chat', headers=headers, json={'session_id':session_id,'message':'需要注意什么？'})
        answer.raise_for_status(); result=answer.json()
        assert result['knowledge_status'] == 'answered' and result['sources']
        assert '[S' in result['reply'] and result['fields'] == first['fields']
        assert result['pending_field'] == first['pending_field']
        checks['grounded_answer_preserves_intake'] = 'passed'
        source = result['sources'][0]
        original = care.get('knowledge/sources/'+source['chunk_id'], headers=headers)
        original.raise_for_status()
        assert original.json()['version'] == source['version'] and original.json()['text']
        assert care.get('knowledge/sources/'+source['chunk_id']).status_code == 401
        checks['authenticated_source_and_version'] = 'passed'
        navigation = care.post('consultations/chat', headers=headers, json={'session_id':session_id,'message':'应该挂什么科？'})
        navigation.raise_for_status(); nav=navigation.json()
        assert nav['recommendations'] and nav['recommendations'][0]['department_id'] == 'respiratory'
        assert '就诊信息整理：' not in nav['reply']
        checks['bookable_department_recommendation'] = 'passed'
        summary = care.post('consultations/chat', headers=headers, json={'session_id':session_id,'message':'重新生成摘要'})
        summary.raise_for_status()
        assert summary.json()['status'] == 'complete'
        department = nav['recommendations'][0]['department_id']
        doctors = care.get(f'departments/{department}/doctors').json()['doctors']
        doctor = doctors[0]['id']
        slots = care.get(f'departments/{department}/slots', params={'doctor_id':doctor}).json()['slots']
        slot = next(row for row in slots if row['remaining'] > 0)
        draft = care.post('appointments/draft', headers=headers, json={
            'session_id':session_id,'department_id':department,'doctor_id':doctor,'slot_id':slot['id']})
        draft.raise_for_status()
        assert draft.json()['status'] == 'pending_confirmation'
        declined = care.post('appointments/'+draft.json()['appointment_id']+'/decision',
                            headers=headers, json={'approved':False})
        declined.raise_for_status()
        assert declined.json()['status'] == 'cancelled'
        checks['appointment_requires_patient_confirmation'] = 'passed' 
        other = care.post('auth/register', json={'username':name+'_2','password':password})
        other.raise_for_status()
        assert care.get('consultations/'+session_id, headers={'Authorization':'Bearer '+other.json()['access_token']}).status_code == 404
        checks['patient_session_isolation'] = 'passed'
        previous = {row['id'] for row in hub.get('queries').json()['queries']}
        urgent = care.post('consultations/chat', headers=headers, json={'session_id':session_id,'message':'我现在胸痛，怎么办？'})
        urgent.raise_for_status(); body=urgent.json()
        assert body['status'] == 'urgent' and body['sources'] == [] and body['recommendations'] == []
        assert {row['id'] for row in hub.get('queries').json()['queries']} == previous
        checks['urgent_bypasses_knowledge'] = 'passed'
    report={'validated_on':datetime.now(timezone.utc).isoformat(),'checks':checks,
            'scope':'real HTTP services, existing databases and configured model APIs'}
    output=ROOT/'.runtime'/'smoke-live.json'; output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for name,state in checks.items():print(name,state,flush=True)
    print('Report: .runtime/smoke-live.json')


if __name__=='__main__':
    main()
