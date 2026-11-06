#!/usr/bin/env python3
"""Real isolated Zabbix 7.4.13; synthetic PSK agent protocol, not Windows execution."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import time

import requests

ROOT = Path('/fixture'); CA = '/tls/ca.crt'
URL = 'https://zabbix.functional.example.test/api_jsonrpc.php'


def main():
    manifest = json.loads((ROOT/'manifest.json').read_text()); run = manifest['run_id']
    assert run.startswith('synthetic-ip-platform-') and os.geteuid() == 0
    assert os.environ['REQUESTS_CA_BUNDLE'] == CA
    evidence = ROOT/'evidence'; stages = []; sequence = 0; session = secrets.token_hex(16)
    def save(name, value):
        p = evidence/name; p.write_text(json.dumps(value,indent=2)); p.chmod(0o600)
    def check(name, observed):
        row = {'stage':name,'result':'PASS','utc':datetime.now(timezone.utc).isoformat(),'observed':observed}
        stages.append(row); save('wsp-stages.private.json', stages); print(json.dumps(row),flush=True)
    auth = None
    def zx(method, params, authenticated=True):
        r = requests.post(URL, json={'jsonrpc':'2.0','method':method,'params':params,'id':1},
                          headers={'Authorization':'Bearer '+auth} if authenticated else {},verify=CA,timeout=30)
        r.raise_for_status(); body = r.json(); assert 'error' not in body,(method,body.get('error')); return body['result']
    assert zx('apiinfo.version',{},False)=='7.4.13'
    auth = zx('user.login',{'username':'Admin','password':'zabbix'},False)
    admin = zx('user.get',{'output':['userid'],'filter':{'username':['Admin']}})[0]
    password = json.loads((ROOT/'secrets/bootstrap.json').read_text())['admin_password']
    zx('user.update',{'userid':admin['userid'],'passwd':password,'current_passwd':'zabbix'})
    auth = zx('user.login',{'username':'Admin','password':password},False)
    token = ROOT/'secrets/wsp-api-token'; token.write_text(auth); token.chmod(0o600)
    assert not any(u['medias'] for u in zx('user.get',{'output':['userid'],'selectMedias':'extend'}))
    baseline_alerts = zx('alert.get',{'output':['alertid']})
    selection = {'output':['hostid','host','name','status','description','tls_connect','tls_accept'],
                 'selectTags':'extend','selectMacros':'extend',
                 'selectInterfaces':['interfaceid','hostid','type','main','useip','ip','dns','port','details'],
                 'selectParentTemplates':['templateid'],'selectHostGroups':['groupid']}
    def canonical(value):
        if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
        if isinstance(value,list):return sorted((canonical(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
        return value
    # Compare configuration, not poller-maintained available/error timestamps.
    # Unordered API result arrays are canonicalized without dropping any fields.
    before_hosts = canonical(zx('host.get',selection))
    save('wsp-outside-hosts-before.private.json',before_hosts)
    group = zx('hostgroup.create',{'name':run})['groupids'][0]
    template = zx('template.get',{'output':['templateid'],'filter':{'host':['Windows by Zabbix agent active']}})[0]['templateid']
    identity = 'wsp-fictitious-'+secrets.token_hex(6); psk = secrets.token_hex(32)
    host = 'synthetic-wsp-win-a'
    hid = zx('host.create',{'host':host,'name':'Synthetic Windows service policy','description':run,'status':0,
        'groups':[{'groupid':group}],'templates':[{'templateid':template}],
        'interfaces':[{'type':1,'main':1,'useip':1,'ip':'192.0.2.90','dns':'','port':'10050'}],
        'tls_connect':2,'tls_accept':2,'tls_psk_identity':identity,'tls_psk':psk,
        'macros':[{'macro':'{$LOCAL.WITNESS}','value':'preserve'}],
        'tags':[{'tag':k,'value':v} for k,v in {'source':'netbox','netbox_id':'77','netbox_object_type':'virtualization.virtualmachine','netbox_monitoring_profile':'windows-active','local':'preserve'}.items()]})['hostids'][0]
    save('wsp-owned-host.private.json',{'hostid':hid,'groupid':group,'owner':run})

    def protocol(payload):
        data = json.dumps(payload).encode(); packet = b'ZBXD\x01'+struct.pack('<Q',len(data))+data
        p = subprocess.run(['openssl','s_client','-connect','zabbix-server:10051','-tls1_2','-cipher','PSK-AES128-GCM-SHA256','-psk_identity',identity,'-psk',psk,'-quiet'],input=packet,capture_output=True,timeout=15)
        if not p.stdout.startswith(b'ZBXD\x01'):
            save('wsp-agent-transport-last.private.json',{'returncode':p.returncode,'stderr':p.stderr.decode(errors='replace')[-1500:]})
            raise AssertionError('Authenticated synthetic-agent response missing')
        size = struct.unpack('<Q',p.stdout[5:13])[0]; return json.loads(p.stdout[13:13+size])

    def items():
        return {i['key_']:i for i in zx('item.get',{'output':['itemid','key_','lastvalue','lastclock','state','error','type'],'hostids':[hid]})}
    def send(values):
        nonlocal sequence
        data=[]; lookup=items()
        for key,value in values.items():
            sequence+=1; data.append({'id':sequence,'itemid':int(lookup[key]['itemid']),'clock':int(time.time()),'ns':time.time_ns()%1000000000,'value':str(value)})
        result=protocol({'request':'agent data','host':host,'session':session,'version':'7.4.13','variant':2,'data':data})
        return result
    def await_condition(fn, label, timeout=100):
        deadline=time.monotonic()+timeout
        while True:
            result=fn()
            if result:return result
            assert time.monotonic()<deadline,label
            time.sleep(1)
    discovery='service.discovery'
    rules=zx('discoveryrule.get',{'output':['itemid','key_'],'hostids':[hid],'filter':{'key_':discovery}}); assert len(rules)==1
    rows=[{'{#SERVICE.NAME}':n,'{#SERVICE.DISPLAYNAME}':d,'{#SERVICE.STARTUP}':0,'{#SERVICE.STARTUPNAME}':'automatic','{#SERVICE.STARTUPTRIGGER}':int(n=='AppXSvc'),'{#SERVICE.STATE}':6,'{#SERVICE.STATENAME}':'stopped','{#SERVICE.PATH}':'synthetic.exe','{#SERVICE.USER}':'LocalSystem','{#SERVICE.DESCRIPTION}':'fictitious'} for n,d in [('AppXSvc','Synthetic AppX service'),('InventorySvc','Synthetic inventory service')]]
    attempts=[]
    def active_ready():
        try:
            r=protocol({'request':'active checks','host':host,'version':'7.4.13','variant':2,'session':session})
            attempts.append({'utc':int(time.time()),'configured':bool(r.get('data'))});save('wsp-active-warmup.private.json',attempts)
            return r if r.get('data') else None
        except (AssertionError,subprocess.TimeoutExpired):
            attempts.append({'utc':int(time.time()),'configured':False,'phase':'new PSK host cache warmup'});save('wsp-active-warmup.private.json',attempts);return None
    active=await_condition(active_ready,'active configuration',timeout=150)
    # LLD has its own API; send its real item ID, never change its type to trapper.
    sequence+=1
    reply=protocol({'request':'agent data','host':host,'session':session,'version':'7.4.13','variant':2,'data':[{'id':sequence,'itemid':int(rules[0]['itemid']),'value':json.dumps(rows),'clock':int(time.time())}]})
    save('wsp-discovery-feed.private.json',reply)
    legacy=await_condition(lambda: (t if len(t:=zx('trigger.get',{'output':['triggerid','description','flags'],'hostids':[hid],'search':{'description':'is not running'}}))==2 else None),'two discovered legacy triggers')
    lookup=items(); oldids={k:v['itemid'] for k,v in lookup.items() if k.startswith('service.info[')}; assert len(oldids)==2
    owned_host_before=canonical(zx('host.get',dict(selection,hostids=[hid]))[0])
    save('wsp-initial-ids.private.json',{'hostid':hid,'host_snapshot':owned_host_before,'legacy_items':oldids,'triggers':legacy})
    accepted=[]
    def old_items_ready():
        r=send({k:6 for k in oldids});accepted.append(r);save('wsp-old-item-cache-warmup.private.json',accepted)
        return r if 'processed: 2;' in r.get('info','') and 'failed: 0;' in r.get('info','') else None
    await_condition(old_items_ready,'new discovered active item cache warmup',timeout=150)
    for _ in range(3):
        r=send({k:6 for k in oldids});assert 'failed: 0;' in r.get('info','');time.sleep(1)
    def actual_history():
        h={k:zx('history.get',{'output':'extend','history':3,'itemids':[iid],'limit':100}) for k,iid in oldids.items()}
        return h if all(h.values()) else None
    histories=await_condition(actual_history,'real old item history stored',timeout=60)
    save('wsp-history-before.private.json',histories)
    check('synthetic-psk-agent-real-lld-history',{'tls':'TLS 1.2 PSK with fictitious identity','real_active_item_types':True,'windows_source':False,'history_rows':{k:len(v) for k,v in histories.items()}})

    spec=importlib.util.spec_from_file_location('wsp','/fixture/windows_service_policy.py'); wsp=importlib.util.module_from_spec(spec);spec.loader.exec_module(wsp)
    cfg={'enabled':True,'phase':'observe','cutover_approved':False,'interval':1,'fault_window':8,'stuck_window':12,'stale_window':30,
         'targets':[{'hostid':hid,'host':host,'netbox_id':'77','object_type':'virtualization.virtualmachine','services':[{'name':n,'display_name':d,'legacy_triggerid':next(t['triggerid'] for t in legacy if '"'+n+'"' in t['description'])} for n,d in [('AppXSvc','Synthetic AppX service'),('InventorySvc','Synthetic inventory service')]]}]}
    api=wsp.API(URL,token,CA);ledger={};save_state=lambda v:wsp.atomic_save(ROOT/'wsp-ledger.private.json',v)
    cfgpath=ROOT/'wsp-config.private.json';cfgpath.write_text(json.dumps(cfg));cfgpath.chmod(0o600)
    import sys
    cli=subprocess.run([sys.executable,'/fixture/windows_service_policy.py','--config',str(cfgpath),'--state',str(ROOT/'wsp-ledger.private.json'),'--url',URL,'--token-file',str(token),'--ca-file',CA],capture_output=True,text=True,timeout=40)
    save('wsp-cli-dry.private.json',{'rc':cli.returncode,'stdout':cli.stdout,'stderr':cli.stderr});assert cli.returncode==0 and json.loads(cli.stdout)['writes']==0
    report=wsp.reconcile(api,cfg,ledger,save_state,apply=False); assert report['writes']==0 and report['changes']==25
    first=wsp.reconcile(api,cfg,ledger,save_state,apply=True);assert first['writes']==25
    assert wsp.reconcile(api,cfg,ledger,save_state,apply=True)['writes']==0
    assert all(t['status']=='1' for t in zx('trigger.get',{'output':['status'],'hostids':[hid],'tags':[wsp.OWNER]}))
    check('observe-plan-apply-repeat',{'planned':25,'created':25,'repeat_writes':0,'replacement_triggers_disabled':True})
    defs,td=wsp.definitions(cfg['targets'][0],cfg);master=defs[0]['key_'];events=[i['key_'] for i in defs if i['key_'].startswith('eventlog.count[')]
    normal=[{'Name':n,'DisplayName':d,'State':'Stopped','StartMode':'Auto','ExitCode':0,'ServiceSpecificExitCode':0} for n,d in [('AppXSvc','Synthetic AppX service'),('InventorySvc','Synthetic inventory service')]]
    def feed(sample=None, failure=0, include_master=True):
        values={k:0 for k in events};values[events[0]]=failure
        if include_master:values[master]=json.dumps(normal if sample is None else sample)
        values.update({k:6 for k in oldids})
        return send(values)
    await_condition(lambda: (r if 'failed: 0;' in (r:=feed()).get('info','') else None),'owned active items in cache')
    for _ in range(4):feed();time.sleep(1)
    await_condition(lambda: all(i['state']=='0' and int(i['lastclock'])>0 for k,i in items().items() if k in {d['key_'] for d in defs}),'all own item preprocessing')
    # Server-side preprocessing is exact production JS, not a Python mock.
    original=items()[master]
    bad_specific=copy.deepcopy(normal);bad_specific[0]['ServiceSpecificExitCode']=5
    negative=copy.deepcopy(normal);negative[0]['ExitCode']=-1
    invalid_state=copy.deepcopy(normal);invalid_state[0]['State']='toString'
    renamed=copy.deepcopy(normal);renamed[0]['DisplayName']='Changed service label'
    cases=[('clean',json.dumps(normal),None),('missing','[]',None),('object','{"invalid":"shape"}','Expected WMI row array'),
           ('duplicate',json.dumps(normal+[normal[0]]),'Unexpected or duplicate'),('negative',json.dumps(negative),'Invalid exit codes'),
           ('inconsistent-specific',json.dumps(bad_specific),'Inconsistent service-specific'),('prototype-name-state',json.dumps(invalid_state),'Unknown service configuration'),
           ('renamed-display',json.dumps(renamed),'Localized display name changed'),('malformed','{bad json','json')]
    pp_results=[]
    for name,value,expected_error in cases:
        sent=int(time.time());reply=send({master:value,**{k:0 for k in events}})
        assert 'failed: 0;' in reply.get('info','')
        def processed():
            row=items()[master]
            if expected_error:return row if row['state']=='1' and expected_error.lower() in row['error'].lower() else None
            return row if row['state']=='0' and int(row['lastclock'])>=sent else None
        result=await_condition(processed,'actual preprocessing '+name,timeout=60)
        if not expected_error:
            parsed=json.loads(result['lastvalue'])
            assert {s:parsed[s]['present'] for s in ['AppXSvc','InventorySvc']}=={s:int(name=='clean') for s in ['AppXSvc','InventorySvc']}
        pp_results.append({'name':name,'expected_error':expected_error,'response':result,'active_data_reply':reply})
        save('wsp-preprocessing.private.json',pp_results)
    for _ in range(4):feed();time.sleep(1)
    await_condition(lambda:items()[master]['state']=='0','valid collection restored before cutover')
    check('exact-production-preprocessing-cases',{'cases':len(cases),'malformed_not_coerced_to_zero':True})
    cfg.update(phase='enforce',cutover_approved=True)
    legacy_events=zx('event.get',{'output':['eventid','objectid','clock','value','acknowledged'],'source':0,'object':0,'objectids':[s['legacy_triggerid'] for s in cfg['targets'][0]['services']],'value':1})
    assert len(legacy_events)>=2,'Legacy problem history must actually exist before cutover'
    save('wsp-legacy-events-before.private.json',legacy_events)
    cut=wsp.reconcile(api,cfg,ledger,save_state,apply=True);assert cut['writes']==12
    assert wsp.reconcile(api,cfg,ledger,save_state,apply=True)['writes']==0
    check('cutover-only-two-old-statuses',{'writes':12,'host_items_templates_history_not_deleted':True,'repeat':0})
    ownedids={d['key_']:items()[d['key_']]['itemid'] for d in defs}
    def problems():
        return zx('problem.get',{'output':['eventid','name'],'hostids':[hid],'tags':[wsp.OWNER],'recent':False})
    def has(kind,service='AppXSvc'):
        return any(p['name']==f'IOP WSP {service}: {kind}' for p in problems())
    assert not problems();check('clean-idle-no-failure',{'services':2,'current_state':'Stopped','exit_code':0})
    failed=copy.deepcopy(normal)
    for _ in range(4):feed(failed,failure=1);time.sleep(1)
    # An API status update is not a cache/evaluation barrier. Keep the fictitious
    # producer alive until the real engine detects the fault, rather than letting
    # an eight-second fixture fault window and thirty-second freshness expire
    # while the newly enabled triggers have not yet entered the server cache.
    detecting_since=time.monotonic()
    def fault_detected():
        reply=feed(failed,failure=1)
        assert 'failed: 0;' in reply.get('info','')
        return has('failure')
    await_condition(fault_detected,'real trigger detects continuously supplied failure',timeout=150)
    detection_wait=round(time.monotonic()-detecting_since,3)
    for _ in range(11):feed();time.sleep(1)
    assert has('failure');check('failure-latches-through-clean-idle-silence',{'SCM_failure_detected':True,'not_recovered_by_silence':True,'fixture_cache_detection_wait_seconds':detection_wait})
    running=copy.deepcopy(normal);running[0]['State']='Running'
    for _ in range(5):feed(running);time.sleep(1)
    await_condition(lambda:not has('failure'),'later running clean recovery')
    check('failure-recovery-requires-later-clean-running',{'recovered_naturally_in_synthetic_data':True,'service_start_commands':0})
    unknown=copy.deepcopy(normal);unknown[0]['ExitCode']=1077
    for _ in range(4):feed(unknown);time.sleep(1)
    assert not has('failure') and items()['iop.wsp[AppXSvc,not_started]']['lastvalue']=='1'
    check('never-started-not-a-crash',{'code':1077,'visible_metric':True})
    exit_failure=copy.deepcopy(normal);exit_failure[0].update(ExitCode=1066,ServiceSpecificExitCode=5)
    for _ in range(5):feed(exit_failure);time.sleep(1)
    await_condition(lambda:has('failure'),'service-specific failure without SCM event')
    running_bad=copy.deepcopy(exit_failure);running_bad[0]['State']='Running'
    for _ in range(3):feed(running_bad);time.sleep(1)
    feed(running);time.sleep(1)
    assert has('failure'),'One clean running observation must not recover previous bad-code observations'
    for _ in range(5):feed(running);time.sleep(1)
    await_condition(lambda:not has('failure'),'service-specific failure recovery')
    check('exit-code-failure-independent-of-event-stream',{'exit_code':1066,'specific_code':5,'SCM_failure_count':0})
    missing=normal[:1]
    for _ in range(4):feed(missing);time.sleep(1)
    await_condition(lambda:has('missing','InventorySvc'),'missing service warning')
    for _ in range(4):feed();time.sleep(1)
    await_condition(lambda:not has('missing','InventorySvc'),'missing service restore')
    drift=copy.deepcopy(normal);drift[1]['StartMode']='Disabled'
    for _ in range(4):feed(drift);time.sleep(1)
    await_condition(lambda:has('startup-drift','InventorySvc'),'configuration drift warning')
    for _ in range(4):feed();time.sleep(1)
    await_condition(lambda:not has('startup-drift','InventorySvc'),'drift restored')
    check('missing-and-config-drift',{'warnings':True,'old_item_ids_preserved':all(items()[k]['itemid']==v for k,v in oldids.items())})
    pending=copy.deepcopy(normal);pending[0]['State']='Start Pending'
    for _ in range(17):feed(pending);time.sleep(1)
    await_condition(lambda:has('transition-stuck'),'stuck transition warning')
    for _ in range(4):feed();time.sleep(1)
    await_condition(lambda:not has('transition-stuck'),'transition clean stop')
    check('sampled-transition-duration',{'configured_seconds':12,'actual_wait_at_least':17})
    # A malformed payload must not become zero/healthy; no fallback preprocessing.
    for _ in range(36):send({master:'{"bad":true}',**{k:0 for k in events}});time.sleep(1)
    await_condition(lambda:has('observation-lost'),'malformed data observation lost',timeout=90)
    assert items()[master]['state']=='1'
    for _ in range(5):feed();time.sleep(1)
    await_condition(lambda:not has('observation-lost'),'observation returns',timeout=90)
    check('malformed-is-unknown-not-healthy',{'unsupported_master_observation_lost':True,'fresh_recovery':True})
    # Discovery/reconcile must not silently undo the deliberate per-ID cutover.
    # Add one explicitly synthetic service as an observable LLD witness; this
    # template version does not materialize SERVICE.DESCRIPTION into item data.
    # The two original service rows are unchanged. Policy must not disable the
    # new, unrelated generic trigger discovered for the synthetic witness.
    rediscovered=copy.deepcopy(rows)
    witness='SyntheticRediscoveryWitness'
    witness_row=copy.deepcopy(rows[0]);witness_row.update({'{#SERVICE.NAME}':witness,'{#SERVICE.DISPLAYNAME}':'Fictitious rediscovery witness','{#SERVICE.STARTUPTRIGGER}':0})
    rediscovered.append(witness_row)
    sequence+=1
    discovery_reply=protocol({'request':'agent data','host':host,'session':session,'version':'7.4.13','variant':2,'data':[{'id':sequence,'itemid':int(rules[0]['itemid']),'value':json.dumps(rediscovered),'clock':int(time.time())}]})
    assert 'processed: 1; failed: 0;' in discovery_reply.get('info','')
    def rediscovery_observed():
        found=zx('item.get',{'output':['itemid','key_'],'hostids':[hid],'filter':{'key_':f'service.info["{witness}",state]'}})
        if len(found)!=1:return None
        rules_found=zx('trigger.get',{'output':['triggerid','status'],'itemids':[found[0]['itemid']]})
        return {'items':found,'triggers':rules_found} if len(rules_found)==1 and rules_found[0]['status']=='0' else None
    witness_before=await_condition(rediscovery_observed,'actual additional synthetic service discovered',timeout=90)
    save('wsp-rediscovery-witness.private.json',witness_before)
    for _ in range(5):feed();time.sleep(1)
    assert wsp.reconcile(api,cfg,ledger,save_state,apply=True)['writes']==0
    assert rediscovery_observed()==witness_before,'Unrelated witness trigger/item changed'
    assert all(t['status']=='1' for t in zx('trigger.get',{'output':['status'],'triggerids':[s['legacy_triggerid'] for s in cfg['targets'][0]['services']]}))
    check('rediscovery-and-reapply',{'additional_synthetic_service_discovered':True,'unrelated_witness_trigger_stays_enabled':True,'old_generic_stays_retired':True,'writes':0})
    rb=wsp.reconcile(api,cfg,ledger,save_state,apply=True,rollback=True);assert rb['writes']==12
    assert wsp.reconcile(api,cfg,ledger,save_state,apply=True,rollback=True)['writes']==0
    assert {k:items()[k]['itemid'] for k in ownedids}==ownedids
    for key,iid in oldids.items():
        assert items()[key]['itemid']==iid
        after=zx('history.get',{'output':'extend','history':3,'itemids':[iid],'time_from':min(int(h['clock']) for h in histories[key]),'limit':2000})
        assert all(h in after for h in histories[key]),'old real history row missing'
    current_host=canonical(zx('host.get',dict(selection,hostids=[hid]))[0])
    save('wsp-owned-host-after.private.json',current_host)
    assert current_host==owned_host_before,'Original host identity/groups/templates/macros/interfaces/TLS changed'
    assert current_host['macros']==[{'hostmacroid':current_host['macros'][0]['hostmacroid'],'macro':'{$LOCAL.WITNESS}','value':'preserve','description':'','type':'0','automatic':'0'}] or any(m['macro']=='{$LOCAL.WITNESS}' and m['value']=='preserve' for m in current_host['macros'])
    assert zx('alert.get',{'output':['alertid']})==baseline_alerts
    retained=zx('event.get',{'output':['eventid','objectid','clock','value','acknowledged'],'eventids':[e['eventid'] for e in legacy_events]})
    assert sorted(retained,key=lambda x:x['eventid'])==sorted(legacy_events,key=lambda x:x['eventid'])
    save('wsp-legacy-events-retained.private.json',retained)
    after_hosts=canonical(zx('host.get',dict(selection,hostids=[h['hostid'] for h in before_hosts])))
    save('wsp-outside-hosts-after.private.json',after_hosts)
    assert after_hosts==before_hosts,'Outside-host configuration changed; compare saved snapshots'
    check('rollback-idempotence-history-and-outside',{'rollback_writes':12,'repeat':0,'history_preserved':True,'alerts_unchanged':True,'other_hosts_unchanged':True})
    save('platform-result.json',{'result':'PASS','stages':stages,'versions':{'zabbix':'7.4.13'},'images':manifest['images'],
        'policy_sha256':hashlib.sha256(Path('/fixture/windows_service_policy.py').read_bytes()).hexdigest(),
        'limitations':['No real Windows WMI/eventlog source tested','Synthetic authenticated active-agent protocol into real Zabbix preprocessing/LLD/trigger engine','Accelerated 1-second sample interval; 8-second fault/12-second transition windows; 30-second nodata','No LAB01 or OPS access','No real service start/stop or crashes induced']})


if __name__=='__main__':main()
