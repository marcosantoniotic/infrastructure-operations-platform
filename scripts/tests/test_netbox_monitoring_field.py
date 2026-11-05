"""Offline explicit-selection contracts. Models/API are mocks, not integration evidence."""
import copy
import json
import os
import io
import types
import unittest
from unittest.mock import patch

import test_netbox_vm_sync as legacy
from test_netbox_platform_mapping import ProfileAPI, PROFILES


class RichAPI(ProfileAPI):
    def call(self, method, params):
        if method == 'item.get':
            tid = params['templateids'][0]
            return [{'type': '3' if tid == '23' else '7', 'key_': 'icmp' if tid == '23' else 'agent.' + tid,
                     'itemid': 'item-' + tid}]
        return super().call(method, params)


class MonitoringFieldTests(unittest.TestCase):
    run_sync = legacy.SyncTests.run_sync

    def setUp(self):
        legacy.SyncTests.setUp(self)
        self.api = RichAPI()
        self.profiles = copy.deepcopy(PROFILES)
        self.profiles['windows-active'] = {'group': 'Windows servers', 'templates': ['Windows by Zabbix agent active', 'ICMP Ping']}
        self.env.update(NETBOX_PLATFORM_MAPPING_ENABLED='true', NETBOX_PLATFORM_MAP='{}',
            NETBOX_PLATFORM_PROFILES=json.dumps(self.profiles), NETBOX_PROFILE_SOURCE='custom-field',
            NETBOX_PROFILE_FIELD='monitoring_profile', NETBOX_PROFILE_VALUES=json.dumps({'linux':'linux-active','windows':'windows-active','icmp':'network-icmp'}),
            NETBOX_PROFILE_LABELS=json.dumps({'linux':'Linux','windows':'Windows','icmp':'ICMP'}))
        self.vms[0].custom_field_data['monitoring_profile'] = 'linux'
        self.real_field_validator = self.g['validate_profile_field']
        self.g['validate_profile_field'] = lambda *a: None

    def definition(self):
        field=types.SimpleNamespace(type='select',choice_set=types.SimpleNamespace(name='iop-monitoring-profiles',choices=[('linux','Linux'),('windows','Windows'),('icmp','ICMP')]),
            label='Perfil de monitoramento',default=None,ui_visible='always',ui_editable='yes',object_types=types.SimpleNamespace(filter=lambda **kw:types.SimpleNamespace(exists=lambda:True)))
        self.g['CustomField']=types.SimpleNamespace(objects=types.SimpleNamespace(filter=lambda **kw:types.SimpleNamespace(first=lambda:field)))
        self.g['ContentType']=types.SimpleNamespace(objects=types.SimpleNamespace(get_for_model=lambda model:types.SimpleNamespace(pk=id(model))))
        self.g['validate_profile_field']=self.real_field_validator
        return field

    def test_single_select_definition_preflight(self):
        self.definition();self.run_sync();self.assertEqual(len(self.api.hosts),1)

    def test_incompatible_field_type_or_default_refused_before_writes(self):
        for kind,default in [('text',None),('multi-select',None),('select','linux')]:
            field=self.definition();field.type=kind;field.default=default
            with self.subTest(kind=kind,default=default),self.assertRaisesRegex(RuntimeError,'custom field'):self.run_sync()
            self.assertEqual(self.api.writes,[])

    def test_hidden_or_noneditable_field_refused(self):
        for prop,value in [('ui_visible','hidden'),('ui_editable','no')]:
            field=self.definition();setattr(field,prop,value)
            with self.subTest(prop=prop),self.assertRaisesRegex(RuntimeError,'visible and editable'):self.run_sync()
            self.assertEqual(self.api.writes,[])

    def test_choice_set_drift_or_missing_vm_assignment_refused(self):
        for change in ['label','field-label','extra','name','object-types']:
            field=self.definition()
            if change=='label':field.choice_set.choices[0]=('linux','Changed')
            elif change=='field-label':field.label='Changed'
            elif change=='extra':field.choice_set.choices.append(('other','Other'))
            elif change=='name':field.choice_set.name='different'
            else:field.object_types.filter=lambda **kw:types.SimpleNamespace(exists=lambda:False)
            with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'custom field'):self.run_sync()
            self.assertEqual(self.api.writes,[])

    def test_explicit_schema_preparation_needs_no_token_or_zabbix_calls(self):
        self.env['ZABBIX_API_TOKEN_FILE']='/not-present-offline'
        self.g['prepare_profile_field']=lambda config:{'created':True,'field_id':1,'choice_set_id':1}
        output=io.StringIO()
        with patch.dict(os.environ,self.env),patch('sys.argv',['sync','--prepare-monitoring-field']),patch('sys.stdout',output):
            self.assertEqual(self.g['main'](),0)
        self.assertTrue(json.loads(output.getvalue())['created']);self.assertEqual(self.api.writes,[])

    def test_explicit_profile_works_without_platform_and_ignores_machine_name(self):
        self.vms[0].name = 'windows-is-only-a-name'
        self.run_sync()
        host = self.api.hosts[0]
        self.assertEqual(host['parentTemplates'], [{'templateid':'21'}])
        self.assertEqual(host['host'], 'netbox-vm-1')
        self.assertIn({'tag':'netbox_monitoring_source','value':'custom-field:monitoring_profile'},host['tags'])
        self.assertEqual(self.vms[0].custom_field_data['monitoring_profile'], 'linux')

    def test_three_profiles_devices_and_vms_and_idempotence(self):
        self.vms.clear()
        for index, value in enumerate(['linux','windows','icmp'],1):
            for objects, kind in [(self.devices,'dcim.device'),(self.vms,'virtualization.virtualmachine')]:
                obj=legacy.obj(index,kind,kind.replace('.','-')+'-'+value)
                obj.custom_field_data['monitoring_profile']=value;objects.append(obj)
        self.run_sync();self.assertEqual(len(self.api.hosts),6)
        windows=[h for h in self.api.hosts if any(t=={'tag':'netbox_monitoring_profile','value':'windows-active'} for t in h['tags'])]
        self.assertEqual(len(windows),2)
        self.assertTrue(all(h['parentTemplates']==[{'templateid':'22'},{'templateid':'23'}] for h in windows))
        self.api.writes.clear();self.run_sync();self.assertEqual(self.api.writes,[])

    def test_blank_unknown_and_rest_style_object_values_refused_before_any_write(self):
        for value in [None,'','unknown',{'value':'linux','label':'Linux'},['linux']]:
            with self.subTest(value=value):
                other=legacy.obj(2);other.custom_field_data['monitoring_profile']=value
                self.vms.append(other)
                with self.assertRaisesRegex(RuntimeError,'custom field'):self.run_sync()
                self.assertEqual(self.api.writes,[]);self.assertNotIn('zabbix_hostid',self.vms[0].custom_field_data)
                self.vms.pop()

    def test_legacy_platform_mapping_migrates_to_field_without_retemplate(self):
        original=dict(self.env)
        self.env.update(NETBOX_PROFILE_SOURCE='platform',NETBOX_PROFILE_VALUES='{}',NETBOX_PROFILE_LABELS='{}',NETBOX_PLATFORM_MAP='{"rhel":"linux-active"}')
        self.vms[0].platform=types.SimpleNamespace(slug='rhel');self.run_sync()
        before=copy.deepcopy(self.api.hosts[0]);self.api.writes.clear();self.env.update(original)
        self.run_sync();after=self.api.hosts[0]
        self.assertEqual([m for m,p in self.api.writes],['host.update'])
        self.assertEqual(set(self.api.writes[0][1]),{'hostid','tags'})
        for k in ['hostid','interfaces','hostgroups','parentTemplates']:self.assertEqual(before[k],after[k])

    def test_silent_return_to_platform_refused_even_with_matching_profile(self):
        self.vms[0].platform=types.SimpleNamespace(slug='rhel');self.run_sync();self.api.writes.clear()
        self.env.update(NETBOX_PROFILE_SOURCE='platform',NETBOX_PROFILE_VALUES='{}',NETBOX_PROFILE_LABELS='{}',NETBOX_PLATFORM_MAP='{"rhel":"linux-active"}')
        with self.assertRaisesRegex(RuntimeError,'custom-field source'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_field_rename_refused_for_existing_host(self):
        self.run_sync();self.api.writes.clear()
        self.env['NETBOX_PROFILE_FIELD']='other_profile';self.vms[0].custom_field_data['other_profile']='linux'
        with self.assertRaisesRegex(RuntimeError,'custom-field source'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_profile_change_requires_explicit_migration_and_preserves_history_links(self):
        self.run_sync();before=copy.deepcopy(self.api.hosts);self.api.writes.clear()
        self.vms[0].custom_field_data['monitoring_profile']='windows'
        with self.assertRaisesRegex(RuntimeError,'group|template|profile'):self.run_sync()
        self.assertEqual(self.api.writes,[]);self.assertEqual(self.api.hosts,before)

    def test_multi_template_missing_link_is_not_added_silently(self):
        self.vms[0].custom_field_data['monitoring_profile']='windows';self.run_sync()
        self.api.hosts[0]['parentTemplates'].pop();self.api.writes.clear()
        with self.assertRaisesRegex(RuntimeError,'template differs'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_multi_template_collision_refused(self):
        call=self.api.call
        self.api.call=lambda method,params: ([{'type':'7','key_':'same-key','itemid':params['templateids'][0]}] if method=='item.get' else call(method,params))
        with self.assertRaisesRegex(RuntimeError,'duplicate item'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_duplicate_resolved_template_identity_refused(self):
        call=self.api.call
        self.api.call=lambda method,params: ([{'templateid':'22'}] if method=='template.get' and params['filter']['name'][0] in ['Windows by Zabbix agent active','ICMP Ping'] else call(method,params))
        with self.assertRaisesRegex(RuntimeError,'Duplicate resolved template'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_multi_template_discovery_key_collision_refused(self):
        call=self.api.call
        self.api.call=lambda method,params: ([{'type':'7','key_':'discovery','itemid':params['templateids'][0]}] if method=='discoveryrule.get' else call(method,params))
        with self.assertRaisesRegex(RuntimeError,'duplicate item'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_multi_template_shared_inherited_identity_does_not_false_positive(self):
        call=self.api.call
        self.api.call=lambda method,params: ([{'type':'7','key_':'shared-key','itemid':'same-item'}] if method=='item.get' else call(method,params))
        self.run_sync();self.assertEqual(len(self.api.hosts),1)

    def test_multiple_templates_still_refuses_unsupported_transport(self):
        call=self.api.call
        self.api.call=lambda method,params: ([{'type':'20','key_':'snmp','itemid':'99'}] if method=='item.get' and params['templateids']==['23'] else call(method,params))
        with self.assertRaisesRegex(RuntimeError,'unsupported interface'):self.run_sync()
        self.assertEqual(self.api.writes,[])

    def test_dry_run_preserves_fields_local_tags_macros_and_templates(self):
        self.run_sync();h=self.api.hosts[0];h['tags'].append({'tag':'owner','value':'keep'});h['macros']=[{'macro':'{$LOCAL}','value':'keep'}]
        before=copy.deepcopy(self.api.hosts);self.api.writes.clear();self.run_sync(False)
        self.assertEqual(self.api.writes,[]);self.assertEqual(self.api.hosts,before)

    def test_invalid_configuration_never_loads_models_or_api(self):
        self.g['setup_netbox']=lambda:self.fail('Invalid config reached Django')
        cases=[{'NETBOX_PROFILE_SOURCE':'tag'}, {'NETBOX_PROFILE_VALUES':'[]'},
            {'NETBOX_PROFILE_VALUES':'{"linux":"missing"}'},{'NETBOX_PROFILE_LABELS':'{}'},
            {'NETBOX_PROFILE_VALUES':'{"linux":"linux-active","linux":"windows-active"}'},
            {'NETBOX_PROFILE_FIELD':'zabbix_hostid'},{'NETBOX_PROFILE_FIELD':'bad-field'},
            {'NETBOX_PROFILE_FIELD':'bad__field'},{'NETBOX_PROFILE_FIELD_LABEL':'x'*51},
            {'NETBOX_PROFILE_CHOICE_SET':'BAD SET'},{'NETBOX_PLATFORM_MAPPING_ENABLED':'false'},
            {'NETBOX_PLATFORM_PROFILES':'{"x":{"group":"g","templates":[]}}'},
            {'NETBOX_PLATFORM_PROFILES':'{"x":{"group":"g","templates":["a","a"]}}'},
            {'NETBOX_PLATFORM_PROFILES':'{"x":{"group":"g","template":"a","templates":["b"]}}'}]
        for env in cases:
            with self.subTest(env=env),patch.dict(self.env,env):
                with self.assertRaises(RuntimeError):self.run_sync()
                self.assertEqual(self.api.writes,[])

    def test_schema_command_is_offline(self):
        self.g['setup_netbox']=lambda:self.fail('Offline validation loaded Django')
        with patch.dict(os.environ,self.env),patch('sys.argv',['sync','--validate-platform-config']):self.assertEqual(self.g['main'](),0)


if __name__=='__main__':unittest.main()
