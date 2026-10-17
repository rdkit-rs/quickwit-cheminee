import importlib.util
import hashlib
import json
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'distribution/cheminee-local'))
from readiness import wait_ready, assert_container_state, container_incarnation, assert_incarnation
spec = importlib.util.spec_from_file_location('measurement_run', HERE / 'run.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class Checks(unittest.TestCase):
    def test_incarnation_changes_fail_closed(self):
        original={'id':'a','restart_count':0,'started_at':'first'}
        assert_incarnation(original,dict(original))
        for after in [dict(original,restart_count=1),dict(original,started_at='second'),dict(original,id='b')]:
            with self.assertRaises(RuntimeError): assert_incarnation(original,after)
        assert_incarnation(original,dict(original,started_at='second'),explicit_restart=True)
        with self.assertRaises(RuntimeError):
            assert_incarnation(original,dict(original,restart_count=1,started_at='second'),explicit_restart=True)
        with self.assertRaises(RuntimeError): assert_incarnation(original,original,explicit_restart=True)

    def test_restart_policy_and_metadata_required(self):
        for policy in ['always','unless-stopped','on-failure']:
            with self.assertRaises(RuntimeError):
                container_incarnation({'HostConfig':{'RestartPolicy':{'Name':policy}}})
        with self.assertRaises(RuntimeError): container_incarnation({})

    def test_startup_503_then_ready(self):
        now = [0.0]
        values = iter([False, urllib.error.HTTPError('', 503, '', {}, None), True])
        def probe(timeout):
            self.assertLessEqual(timeout, 3)
            value = next(values)
            if isinstance(value, Exception):
                raise value
            return value
        wait_ready(probe, timeout=1, clock=lambda: now[0],
                   sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertEqual(now[0], .5)

    def test_wrong_type_does_not_establish_readiness(self):
        now = [0.0]
        with self.assertRaises(TimeoutError):
            wait_ready(lambda timeout: {'ready': True}, timeout=.5,
                       clock=lambda: now[0], sleep=lambda t: now.__setitem__(0, now[0] + t))
        self.assertEqual(now[0], .5)

    def test_late_success_rejected(self):
        now = [0.0]
        def probe(timeout):
            now[0] = 2.0
            return True
        with self.assertRaises(TimeoutError):
            wait_ready(probe, timeout=1, clock=lambda: now[0], sleep=lambda _: None)

    def test_auth_failure_is_immediate(self):
        def probe(timeout):
            raise urllib.error.HTTPError('', 401, '', {}, None)
        with self.assertRaises(urllib.error.HTTPError):
            wait_ready(probe, sleep=lambda _: self.fail('must not retry auth failure'))

    def test_final_container_failure(self):
        for state in ({}, {'Running': True, 'OOMKilled': True, 'Health': {'Status': 'healthy'}},
                      {'Running': True, 'OOMKilled': False, 'Health': {'Status': 'unhealthy'}}):
            with self.assertRaises(RuntimeError):
                assert_container_state(state)

    def test_remote_docker_host_rejected(self):
        with patch.dict(run.os.environ, {'DOCKER_HOST': 'tcp://remote:2375'}, clear=True):
            with self.assertRaises(ValueError):
                run.require_local_docker()

    def test_context_overrides_host(self):
        with patch.dict(run.os.environ, {'DOCKER_CONTEXT': 'remote', 'DOCKER_HOST': 'unix:///local'}, clear=True):
            with patch.object(run.subprocess, 'check_output', return_value='[{"Endpoints":{"docker":{"Host":"ssh://remote"}}}]'):
                with self.assertRaises(ValueError):
                    run.require_local_docker()

    def test_admission_and_budget_failure_do_not_execute(self):
        image = 'sha256:' + 'a' * 64
        info = {'Id': 'id', 'Image': image, 'RestartCount': 0, 'State': {'StartedAt': 'initial', 'Running': True, 'OOMKilled': False,
                'Health': {'Status': 'healthy'}}, 'HostConfig': {'RestartPolicy': {'Name': 'no'}, 'Memory': 1024, 'MemorySwap': 1024, 'NanoCpus': 1000000000},
                'Mounts': [], 'NetworkSettings': {'Ports': {'7280/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '7280'}]}}}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            provenance = folder / 'provenance.json'
            provenance.write_text(json.dumps({'image_id': image,
                'source_commit': 'c' * 40, 'binary_sha256': 'b' * 64}))
            for case, (memory, revision, expected) in enumerate([(1024, 'c' * 40, 0), (1, 'c' * 40, 1), (1024, 'd' * 40, 1), (1024, 'short', 1)]):
                output = folder / str(case)
                argv = ['run.py', '--output', str(output), '--image', image,
                    '--storage-path', temporary, '--min-free-bytes', '1',
                    '--memory-budget-bytes', str(memory), '--cpu-budget', '1',
                    '--source-commit', revision, '--runtime-provenance', str(provenance), '--runtime-provenance-sha256',
                    hashlib.sha256(provenance.read_bytes()).hexdigest()]
                with patch.object(sys, 'argv', argv), patch.object(run, 'require_local_docker', return_value='unix:///local'), \
                        patch.object(run, 'inspect_container', return_value=info), \
                        patch.object(run.subprocess, 'check_output', return_value=temporary), \
                        patch.object(run.subprocess, 'run') as execute:
                    self.assertEqual(run.main(), expected)
                    execute.assert_not_called()
                report = json.loads((output / 'admission.json').read_text())
                self.assertEqual(report['expected_source_commit'], revision)
                self.assertEqual(report['live_measurements'], 'pending')
                self.assertEqual(report['status'], 'failed' if expected else 'admitted_not_executed')

    def test_image_and_resource_checks(self):
        image = 'sha256:' + 'a' * 64
        info = {'Id': 'id', 'Image': image, 'RestartCount': 0, 'State': {'StartedAt': 'initial', 'Running': True, 'OOMKilled': False,
                'Health': {'Status': 'healthy'}}, 'HostConfig': {'RestartPolicy': {'Name': 'no'}, 'Memory': 1024, 'MemorySwap': 1024, 'NanoCpus': 1000000000}}
        self.assertEqual(run.check_container(info, image)['cpu_limit'], 1)
        for bad in ['latest', 'sha256:' + 'b' * 64]:
            with self.assertRaises(ValueError):
                run.check_container(info, bad)
        info['HostConfig']['MemorySwap'] = -1
        with self.assertRaises(ValueError):
            run.check_container(info, image)
        info['HostConfig']['MemorySwap'] = 1024
        info['HostConfig']['Memory'] = 0
        with self.assertRaises(ValueError):
            run.check_container(info, image)


if __name__ == '__main__':
    unittest.main()
