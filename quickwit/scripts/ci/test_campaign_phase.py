#!/usr/bin/env python3
"""Tiny-process safety tests; never invokes Cargo, Docker or disk-filling workloads."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).with_name('campaign_phase.py').resolve()
spec=importlib.util.spec_from_file_location('campaign_phase',SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.policy={'reserve_mib':1,'emergency_floor_mib':1,'lock_path':str(self.root/'lock'),
          'phases':{'tiny':{'growth_budget_mib':2,'timeout_seconds':5,'command':[sys.executable,'-c','pass']}}}
        self.policy_path=self.root/'policy.json';self.save_policy()
    def tearDown(self):self.tmp.cleanup()
    def save_policy(self):self.policy_path.write_text(json.dumps(self.policy))
    def args(self,name='job',dry=True):
        return types.SimpleNamespace(policy=self.policy_path,phase='tiny',state=self.root/(name+'.json'),
          log=self.root/(name+'.log'),filesystem=self.root,admit_only=dry,preflight=None,reviewed_prior_state_sha256=None)
    def command(self,name='job'):
        return [sys.executable,str(SCRIPT),'run','--phase','tiny','--policy',str(self.policy_path),
          '--state',str(self.root/(name+'.json')),'--log',str(self.root/(name+'.log')),'--filesystem',str(self.root)]
    def wait_running(self,name='job'):
        path=self.root/(name+'.json');deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if path.exists():
                v=json.loads(path.read_text())
                if v.get('status')=='running':return v
            time.sleep(.02)
        self.fail('runner did not enter running')
    def test_admission_boundary(self):
        for free,expected,name in [(3*m.MIB,0,'yes'),(3*m.MIB-1,2,'no')]:
            with patch.object(m.shutil,'disk_usage',return_value=types.SimpleNamespace(free=free)):
                self.assertEqual(m.run(self.args(name)),expected)
            self.assertFalse((self.root/(name+'.log')).exists())
    def test_invalid_numbers_and_unknown_budget(self):
        for key in ['growth_budget_mib','timeout_seconds']:
            for value in [True,-1,0,1.5,float('nan'),float('inf')]:
                phase=dict(self.policy['phases']['tiny'],**{key:value})
                with self.assertRaises(ValueError):m.validate_policy(self.policy,phase)
        for key in ['reserve_mib','emergency_floor_mib']:
            with self.assertRaises(ValueError):m.validate_policy(dict(self.policy,**{key:float('nan')}),self.policy['phases']['tiny'])
        self.policy['phases']['tiny']['growth_budget_mib']=None;self.save_policy()
        self.assertEqual(m.run(self.args()),2)
    def test_final_sample_is_minimum(self):
        args=self.args(dry=False)
        with patch.object(m.shutil,'disk_usage',side_effect=[types.SimpleNamespace(free=9*m.MIB),types.SimpleNamespace(free=8*m.MIB)]), patch.object(m,'group_members',return_value=[]),patch.object(m,'unmanaged_builds',return_value=[]):
            child=types.SimpleNamespace(pid=999999,poll=lambda:0,wait=lambda:0)
            with patch.object(m.subprocess,'Popen',return_value=child),patch.object(m,'identity',return_value={'start_ticks':'1'}):
                self.assertEqual(m.run(args),0)
        state=json.loads(args.state.read_text());self.assertEqual(state['minimum_observed_free_bytes'],8*m.MIB)
    def test_concurrent_lock_survives_supervisor_death(self):
        self.policy['phases']['tiny']['command']=[sys.executable,'-c','import time; time.sleep(4)'];self.save_policy()
        runner=subprocess.Popen(self.command(),stdout=subprocess.DEVNULL)
        state=self.wait_running()
        try:
            other=subprocess.run(self.command('second'),capture_output=True,timeout=5)
            self.assertEqual(other.returncode,3)
            runner.kill();runner.wait()
            other=subprocess.run(self.command('third'),capture_output=True,timeout=5)
            self.assertEqual(other.returncode,3)
        finally:
            m.stop_group(state['child_pid'])
            if runner.poll() is None:runner.kill();runner.wait()
        # A disconnected runner is not silently treated as a successful terminal job.
        other=subprocess.run(self.command('fourth'),capture_output=True,timeout=5)
        self.assertNotEqual(other.returncode,0)
    def test_term_resistant_grandchild_is_killed(self):
        code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)']); time.sleep(60)"
        self.policy['phases']['tiny'].update(command=[sys.executable,'-c',code],timeout_seconds=1);self.save_policy()
        runner=subprocess.Popen(self.command(),stdout=subprocess.DEVNULL)
        state=self.wait_running()
        try:
            self.assertEqual(runner.wait(timeout=25),1)
            self.assertFalse(m.group_members(state['child_pid']))
            self.assertEqual(json.loads((self.root/'job.json').read_text())['status'],'timed_out')
        finally:
            m.stop_group(state['child_pid'])
            if runner.poll() is None:runner.kill();runner.wait()
    def test_durable_intent_failure_prevents_launch(self):
        with patch.object(m,'write_state',side_effect=OSError('injected')),patch.object(m.subprocess,'Popen') as spawn:
            with self.assertRaises(OSError):m.run(self.args(dry=False))
            spawn.assert_not_called()
    def test_preflight_future_or_incomplete_refused(self):
        report={'status':'passed','cwd':str(self.root),'created_unix':time.time()+100,'file_hashes':{}}
        path=self.root/'preflight.json';path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):m.check_preflight(path,self.root)
        report['created_unix']=time.time();path.write_text(json.dumps(report))
        with self.assertRaises((KeyError,ValueError)):m.check_preflight(path,self.root)
    def test_namespace_mismatch_is_not_restartable(self):
        state={'status':'running','child_pid':os.getpid(),'pid_namespace':'another','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
        path=self.root/'prior.json';path.write_text(json.dumps(state))
        lock=self.root/'lock';lock.write_text(str(path))
        self.assertIn('different_pid_namespace',m.inspect_state(path)['inspection'])
        with self.assertRaises(ValueError):m.run(self.args())

    def test_unknown_prior_state_requires_review(self):
        for index, state in enumerate([{}, {'status':'checking_admission'}, {'status':'invented'}]):
            path=self.root/('prior'+str(index)+'.json');path.write_text(json.dumps(state))
            lock=self.root/('lock'+str(index));lock.write_text(str(path))
            with lock.open() as stream:
                with self.assertRaises(ValueError):m.inspect_previous(stream,None)
            with lock.open() as stream:
                m.inspect_previous(stream,hashlib.sha256(path.read_bytes()).hexdigest())
    def test_reviewed_terminal_from_old_boot(self):
        path=self.root/'old.json';path.write_text(json.dumps({'status':'completed','child_pid':999999,'boot_id':'old','pid_namespace':'old'}))
        lock=self.root/'lock';lock.write_text(str(path))
        with lock.open() as stream:
            with self.assertRaises(ValueError):m.inspect_previous(stream,None)
        with lock.open() as stream:m.inspect_previous(stream,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_path_aliases_and_existing_temporary_refused(self):
        args=self.args()
        args.log=args.state
        with self.assertRaises(ValueError):m.run(args)
        args=self.args()
        args.log=args.state.with_name(args.state.name+'.tmp')
        with self.assertRaises(ValueError):m.run(args)
        args=self.args()
        temporary=args.state.with_name(args.state.name+'.tmp')
        temporary.symlink_to(self.root/'missing')
        with self.assertRaises(ValueError):m.run(args)
        self.assertTrue(temporary.is_symlink())


if __name__=='__main__':unittest.main()
