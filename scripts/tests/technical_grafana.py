"""Real Grafana signed-plugin checks inside the new synthetic API fixture."""
import copy,json,time,secrets,os
from pathlib import Path
import requests

class TechnicalGrafana:
 def __init__(self,root,zx,hosts,owned,tech_ids,check):
  self.root=root;self.zx=zx;self.hosts=hosts;self.owned=set(owned.values());self.ids=tech_ids;self.check=check
  self.session=requests.Session();self.session.auth=('admin',(root/'secrets/grafana-admin').read_text().strip());self.base='http://grafana:3000'
  deadline=time.monotonic()+120
  while True:
   try:
    if self.req('GET','/api/health').get('database')=='ok':break
   except Exception:pass
   assert time.monotonic()<deadline;time.sleep(2)
  self.req('POST','/api/plugins/alexanderzobnin-zabbix-app/settings',{'enabled':True,'pinned':False})
  meta=self.req('GET','/api/plugins/alexanderzobnin-zabbix-app/settings')
  check('grafana-official-signature',meta['signature']=='valid' and meta['info']['version']=='6.10.2',{'version':meta['info']['version'],'signature':meta['signature']})
  self.seed()
  passwd=(secrets.token_urlsafe(36))
  group=zx('usergroup.create',{'name':'Fixture Grafana Technical Reader','hostgroup_rights':[{'id':v,'permission':2} for v in tech_ids.values()]})['usrgrpids'][0]
  zx('user.create',{'username':'fixture-technical-reader','passwd':passwd,'roleid':'1','usrgrps':[{'usrgrpid':group}]})
  self.ds={'uid':'iop-zabbix-readonly','name':'IOP Zabbix read only','type':'alexanderzobnin-zabbix-datasource','access':'proxy','url':'https://zabbix.functional.example.test/api_jsonrpc.php','jsonData':{'username':'fixture-technical-reader','authType':'userLogin','tlsSkipVerify':False,'tlsAuthWithCACert':True,'dbConnectionEnable':False,'cacheTTL':'1s','disableReadOnlyUsersAck':True},'secureJsonData':{'password':passwd,'tlsCACert':(root/'tls/ca.crt').read_text()}}
  self.req('POST','/api/datasources',self.ds)
  health=self.req('GET','/api/datasources/uid/iop-zabbix-readonly/health');check('grafana-reader-tls-health',health['status']=='OK',{'status':health['status']})
  for title,edit in [('wrong-ca',{'secureJsonData':{'tlsCACert':''}}),('wrong-hostname',{'url':'https://proxy/api_jsonrpc.php'})]:
   bad=copy.deepcopy(self.ds);bad['uid']='negative-'+title;bad['name']='Negative '+title
   if 'secureJsonData' in edit:bad['secureJsonData'].update(edit['secureJsonData'])
   else:bad.update(edit)
   self.req('POST','/api/datasources',bad)
   response=self.session.get(self.base+'/api/datasources/uid/'+bad['uid']+'/health',timeout=30)
   check('grafana-'+title+'-blocked',response.status_code!=200 or response.json().get('status')!='OK',{'status':response.status_code})
   self.req('DELETE','/api/datasources/uid/'+bad['uid'])
  resource='/api/datasources/uid/iop-zabbix-readonly/resources/zabbix-api'
  denied=self.session.post(self.base+resource,json={'method':'host.update','params':{'hostid':next(iter(self.owned)),'name':'MUST-NOT-WRITE'}},timeout=30)
  check('grafana-reader-write-refused',denied.status_code>=400,{'status':denied.status_code})
  self.before={}
  for p in (root/'baseline-dashboards').glob('*.json'):
   db=json.loads(p.read_text());self.req('POST','/api/dashboards/db',{'dashboard':db,'overwrite':False});self.before[db['uid']]=self.req('GET','/api/dashboards/uid/'+db['uid'])['dashboard']
  assert len(self.before)==6
  for p in (root/'group-dashboards').glob('*.json'):
   db=json.loads(p.read_text());assert db['uid'] not in self.before
   self.req('POST','/api/dashboards/db',{'dashboard':db,'overwrite':False})
  check('grafana-four-import-six-preserved',all(v==self.req('GET','/api/dashboards/uid/'+k)['dashboard'] for k,v in self.before.items()),{'new':4,'preserved':6})
  self.query_matrix('before-transition')
  if os.environ.get('IOP_TECHNICAL_VISUAL_TEST','0')=='1':self.visual_review()
 def visual_review(self):
  password=(secrets.token_urlsafe(36))
  (self.root/'secrets/grafana-viewer').write_text(password)
  self.req('POST','/api/admin/users',{'name':'Synthetic Viewer','login':'fixture-viewer','email':'fixture-viewer@example.test','password':password,'OrgId':1})
  # Only newly-created owned IDs; do not mix probes of documentation addresses
  # with deliberately synthetic trapper series during browser review.
  checks=self.zx('item.get',{'output':['itemid','hostid','status'],'hostids':list(self.owned),'filter':{'key_':['icmpping','icmppingloss','icmppingsec']}})
  assert all(i['hostid'] in self.owned for i in checks)
  try:
   if checks:self.zx('item.update',[{'itemid':i['itemid'],'status':1} for i in checks])
   for hid in self.original:self.zx('host.update',{'hostid':hid,'status':0})
   (self.root/'visual-ready').write_text('Owned synthetic hosts ready; official signed plugin')
   deadline=time.monotonic()+600
   while not (self.root/'visual-complete').exists():
    assert time.monotonic()<deadline,'Visual review window expired'
    time.sleep(2)
  finally:
   for hid,status in self.original.items():self.zx('host.update',{'hostid':hid,'status':int(status)})
   if checks:self.zx('item.update',[{'itemid':i['itemid'],'status':int(i['status'])} for i in checks])
 def req(self,method,path,payload=None):
  q=self.session.request(method,self.base+path,json=payload,timeout=45);q.raise_for_status();return q.json()
 def seed(self):
  self.items=[];self.original={}
  for h in self.hosts():
   if h['hostid'] not in self.owned:continue
   self.original[h['hostid']]=h['status'];profile=next(t['value'] for t in h['tags'] if t['tag']=='netbox_monitoring_profile')
   self.zx('host.update',{'hostid':h['hostid'],'status':0})
   metrics=[('ICMP ping','ping','',1),('ICMP loss','loss','%',0),('ICMP response time','latency','s',.012)]
   if profile!='network-icmp':metrics += [('CPU utilization','cpu','%',24),('Memory utilization','memory','%',47),('FS [/]: Space: Used, in %','disk','%',38),('Interface fixture0: Bits received','network','bps',12000)]
   if profile=='windows-active':metrics += [('State of service "FixtureService"','service','',0)]
   for name,key,unit,value in metrics:
    item=self.zx('item.create',{'hostid':h['hostid'],'name':name,'key_':'synthetic.dashboard.'+key,'units':unit,'type':2,'value_type':0,'delay':'0'})['itemids'][0]
    self.items.append((item,value,key))
  deadline=time.monotonic()+100
  while True:
   now=int(time.time());result=self.zx('history.push',[{'itemid':i,'clock':now,'value':str(v)} for i,v,k in self.items]);errors=[r.get('error') for r in result['data'] if r.get('error')]
   if not errors:break
   assert time.monotonic()<deadline;time.sleep(3)
  self.zx('history.push',[{'itemid':i,'clock':int(time.time())-60*m,'value':str(v)} for i,v,k in self.items for m in range(1,20)])
  for hid,status in self.original.items():self.zx('host.update',{'hostid':hid,'status':int(status)})
 def query_matrix(self,phase):
  for profile,gid in self.ids.items():
   expected={h['hostid'] for h in self.hosts() if gid in {g['groupid'] for g in h['hostgroups']}}
   group={'linux-active':'IOP - Linux','windows-active':'IOP - Windows','network-icmp':'IOP - ICMP'}[profile]
   response=self.req('POST','/api/ds/query',{'from':str((int(time.time())-3600)*1000),'to':str(int(time.time())*1000),'queries':[{'refId':'A','datasource':{'type':self.ds['type'],'uid':self.ds['uid']},'queryType':'0','schema':13,'group':{'filter':group},'host':{'filter':'/.*/'},'application':{'filter':''},'itemTag':{'filter':''},'item':{'filter':'ICMP ping'},'functions':[],'options':{'useTrends':'false','showDisabledItems':True},'intervalMs':1000,'maxDataPoints':500}]})
   a=response['results']['A'];assert not a.get('error')
   actual=set()
   for frame in a.get('frames',[]):
    for field in frame['schema']['fields']:
     if field['type']=='number':actual.add(field.get('labels',{}).get('host'))
   expected_names={h['name'] for h in self.hosts() if h['hostid'] in expected}
   self.check('grafana-group-'+profile+'-'+phase,actual==expected_names,{'expected_hosts':len(expected_names),'returned_hosts':len(actual),'no_hostTags':True})
 def finalize(self):
  time.sleep(2);self.query_matrix('after-transition')
  self.check('grafana-six-still-preserved',all(v==self.req('GET','/api/dashboards/uid/'+k)['dashboard'] for k,v in self.before.items()),{'preserved':6})
