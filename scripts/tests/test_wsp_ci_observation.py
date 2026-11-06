"""Offline timing/privacy regressions; no sockets, Windows or runtime APIs."""
import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from wsp_ci_observation import failure_report,public_failure_report,wait_next_second

ROOT=Path(__file__).resolve().parents[2]

class Clock:
    def __init__(self,value):self.value=value;self.elapsed=0;self.pauses=0
    def wall(self):return self.value+self.elapsed
    def mono(self):return self.elapsed
    def pause(self,seconds):self.elapsed+=seconds;self.pauses+=1

class ObservationTests(unittest.TestCase):
    def test_same_second_waits_until_strictly_new_source_second(self):
        clock=Clock(2000000000.8)
        sent=wait_next_second(2000000000,clock.wall,clock.mono,clock.pause)
        self.assertEqual(sent,2000000001);self.assertGreater(clock.pauses,0)
        self.assertLess(clock.elapsed,1)
    def test_actual_processing_predicate_cannot_accept_previous_payload_after_fence(self):
        tree=ast.parse((ROOT/'scripts/tests/functional_windows_service_policy.py').read_text())
        predicate=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='processed')
        clock=Clock(2000000000.8);previous=2000000000
        row={'state':'0','lastclock':str(previous),'lastvalue':'{"AppXSvc":{"present":1}}'}
        scope={'items':lambda:{'master':row},'master':'master','sent':previous,'expected_error':None}
        exec(compile(ast.Module(body=[predicate],type_ignores=[]),'actual-predicate','exec'),scope)
        self.assertIs(scope['processed'](),row,'This reproduces the old, unfenced false-fresh result')
        scope['sent']=wait_next_second(previous,clock.wall,clock.mono,clock.pause)
        self.assertIsNone(scope['processed'](),'Stale clean payload cannot satisfy new missing control')
        row.update(lastclock=str(scope['sent']),lastvalue='{"AppXSvc":{"present":0}}')
        self.assertIs(scope['processed'](),row)
        self.assertEqual(json.loads(row['lastvalue'])['AppXSvc']['present'],0)
    def test_future_or_stopped_clock_fails_without_synthetic_future_timestamp(self):
        for previous in (2000000000,2000000050):
            with self.subTest(previous=previous):
                clock=Clock(2000000000)
                with self.assertRaises(TimeoutError):
                    wait_next_second(previous,lambda:2000000000,clock.mono,clock.pause,timeout=0.1)
    def test_invalid_fence_inputs_refused(self):
        for value in (-1,True,2.0,'2'):
            with self.subTest(value=value),self.assertRaises(ValueError):wait_next_second(value)
        for timeout in (0,-1,4,True,float('nan'),'1'):
            with self.subTest(timeout=timeout),self.assertRaises(ValueError):wait_next_second(0,timeout=timeout)
    def test_already_advanced_clock_does_not_sleep(self):
        clock=Clock(2000000002)
        self.assertEqual(wait_next_second(2000000000,clock.wall,clock.mono,clock.pause),2000000002)
        self.assertEqual(clock.pauses,0)
    def test_fence_uses_last_submitted_even_if_item_get_is_older(self):
        clock=Clock(2000000001.8)
        last_visible=2000000000;last_submitted=2000000001
        sent=wait_next_second(last_submitted,clock.wall,clock.mono,clock.pause)
        self.assertGreater(sent,last_visible)
        self.assertGreater(sent,last_submitted,'Even an earlier queued sample must be behind the new fence')
    def test_diagnostic_drops_messages_commands_tokens_and_unknown_frames(self):
        sentinel='DO-NOT-PUBLISH-PSK-OR-TOKEN'
        value={'exception':'TimeoutExpired','message':sentinel,'command':['openssl','-psk',sentinel],
               'frames':[{'file':'functional-platform.py','line':42,'locals':sentinel},
                         {'file':sentinel,'line':1},{'file':'functional-platform.py','line':True}]}
        safe=public_failure_report(value)
        self.assertNotIn(sentinel,json.dumps(safe))
        self.assertEqual(safe,{'result':'FAIL','exception':'TimeoutExpired','frames':[{'file':'functional-platform.py','line':42}]})
    def test_malformed_diagnostic_is_bounded_and_does_not_raise(self):
        for value in (None,[],{'exception':[],'frames':[{'file':[],'line':1}]},
                      {'exception':{'secret':'x'},'frames':'secret'}):
            self.assertEqual(public_failure_report(value),{'result':'FAIL','exception':'Exception','frames':[]})
        value={'exception':'RuntimeError','frames':[{'file':'functional-platform.py','line':1}]*100}
        self.assertEqual(len(public_failure_report(value)['frames']),8)
    def test_exception_report_never_serializes_exception_message(self):
        try:raise RuntimeError('secret-password-cookie-psk')
        except RuntimeError as error:safe=failure_report(error)
        self.assertEqual(safe,{'result':'FAIL','exception':'RuntimeError','frames':[]})
    def test_only_known_check_identifiers_can_be_published(self):
        safe=failure_report(AssertionError('preprocessing_presence_mismatch'))
        self.assertEqual(safe['check'],'preprocessing_presence_mismatch')
        self.assertNotIn('check',public_failure_report({'check':'secret-password'}))
        self.assertNotIn('check',public_failure_report({'check':['preprocessing_presence_mismatch']}))
    def test_wrapper_prints_only_sanitized_failure_file(self):
        spec=importlib.util.spec_from_file_location('wsp_runner',ROOT/'scripts/ci/test-windows-service-policy.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            # Only the path predicate is substituted here; actual file parser
            # and stdout serializer run. No operational paths are read.
            work=Path(directory);(work/'evidence').mkdir()
            (work/'evidence/wsp-ci-failure.sanitized.json').write_text(json.dumps(
                {'exception':'AssertionError','frames':[{'file':'functional-platform.py','line':222}],
                 'message':'never-public-secret'}))
            output=io.StringIO()
            class DisposablePath:
                def resolve(self):return self
                def __str__(self):return '/tmp/synthetic-fixture'
                def __truediv__(self,name):return work/name
            with patch.object(runner.argparse.ArgumentParser,'parse_known_args',return_value=(type('Args',(),{'workspace':DisposablePath()})(),[])),\
                 contextlib.redirect_stdout(output):runner.emit_failure_diagnostic(ROOT)
            self.assertNotIn('never-public-secret',output.getvalue())
            self.assertIn('WSP_CI_DIAGNOSTIC',output.getvalue())

if __name__=='__main__':unittest.main()
