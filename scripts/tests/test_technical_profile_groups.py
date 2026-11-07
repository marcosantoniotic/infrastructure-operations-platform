import importlib.machinery,importlib.util,os,unittest,copy,json
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parents[2]/'roles/netbox_zabbix_sync/templates/netbox-zabbix-sync.py.j2'
loader=importlib.machinery.SourceFileLoader('sync_technical',str(P));spec=importlib.util.spec_from_loader(loader.name,loader);s=importlib.util.module_from_spec(spec);loader.exec_module(s)
IDS={'linux-active':'101','windows-active':'102','legacy-icmp':'103'}
def host(groups=('1','77'),marker=None):
 h={'hostgroups':[{'groupid':g} for g in groups],'tags':[{'tag':'local','value':'keep'}]}
 if marker:h['tags'].append({'tag':'netbox_technical_group','value':marker})
 return h
class Tests(unittest.TestCase):
 def test_disabled_unchanged(self):self.assertIsNone(s.technical_group_plan(host(),None,{}))
 def test_adopt_keeps_local(self):
  h=host();old=copy.deepcopy(h);p=s.technical_group_plan(h,'linux-active',IDS);self.assertEqual(h,old);self.assertEqual({g['groupid'] for g in p['groups']},{'1','77','101'})
 def test_exactly_one_owned_transition(self):
  p=s.technical_group_plan(host(('1','77','101'),'v1:linux-active:101'),'windows-active',IDS)
  self.assertEqual({g['groupid'] for g in p['groups']},{'1','77','102'});self.assertEqual(p['marker'],'v1:windows-active:102')
 def test_repeat_no_change(self):self.assertFalse(s.technical_group_plan(host(('1','77','102'),'v1:windows-active:102'),'windows-active',IDS)['changed'])
 def test_removal_refused(self):
  with self.assertRaises(RuntimeError):s.technical_group_plan(host(('101',),'v1:linux-active:101'),'linux-active',{})
 def test_unowned_group_refused(self):
  with self.assertRaises(RuntimeError):s.technical_group_plan(host(('1','101')),'linux-active',IDS)
 def test_duplicate_technical_membership_refused(self):
  with self.assertRaises(RuntimeError):s.technical_group_plan(host(('101','102'),'v1:linux-active:101'),'linux-active',IDS)
 def test_marker_tamper_refused(self):
  for marker in ['v1:linux-active:999','bad','v1:absent:101']:
   with self.subTest(marker=marker),self.assertRaises(RuntimeError):s.technical_group_plan(host(('101',),marker),'linux-active',IDS)
 def test_missing_owned_membership_refused(self):
  with self.assertRaises(RuntimeError):s.technical_group_plan(host(('1',),'v1:linux-active:101'),'linux-active',IDS)
 def test_group_remap_refused(self):
  with self.assertRaises(RuntimeError):s.technical_group_plan(host(('101',),'v1:linux-active:101'),'linux-active',{**IDS,'linux-active':'104'})
 def test_invalid_catalogue_refused(self):
  for ids in [{**IDS,'windows-active':'101'},{**IDS,'windows-active':'bad'}]:
   with self.assertRaises(RuntimeError):s.technical_group_plan(host(),'linux-active',ids)
 def test_base_group_plan_cannot_mix_profiles(self):
  with self.assertRaises(RuntimeError):s.technical_group_plan(host(),'linux-active',IDS,[{'groupid':'102'}])
 def test_configuration_requires_optin_and_full_map(self):
  profiles={'linux-active':{'group':'Linux servers'}}
  for env in [{'NETBOX_TECHNICAL_GROUPS_ENABLED':'yes'},{'NETBOX_TECHNICAL_GROUPS':'{"linux-active":"IOP - Linux"}'},{'NETBOX_TECHNICAL_GROUPS_ENABLED':'true','NETBOX_TECHNICAL_GROUPS':'{}'},{'NETBOX_TECHNICAL_GROUPS_ENABLED':'true','NETBOX_TECHNICAL_GROUPS':'{"linux-active":"Linux servers"}'}]:
   with patch.dict(os.environ,env,clear=True),self.assertRaises(RuntimeError):s.load_technical_groups(profiles,{})
  with patch.dict(os.environ,{'NETBOX_TECHNICAL_GROUPS_ENABLED':'true','NETBOX_TECHNICAL_GROUPS':json.dumps({'linux-active':'IOP - Linux'})},clear=True):self.assertEqual(s.load_technical_groups(profiles,{}),{'linux-active':'IOP - Linux'})
 def test_unsafe_group_names_refused(self):
  for name in [' leading','trailing ','new\nline','nul\x00byte','dollar$group']:
   with self.subTest(name=name),patch.dict(os.environ,{'NETBOX_TECHNICAL_GROUPS_ENABLED':'true','NETBOX_TECHNICAL_GROUPS':json.dumps({'linux-active':name})},clear=True),self.assertRaises(RuntimeError):
    s.load_technical_groups({'linux-active':{'group':'Linux servers'}},{})
if __name__=='__main__':unittest.main()
