"""Bounded readiness checks; never retries writes or query correctness failures."""
import subprocess
import time
import urllib.error


def wait_ready(probe, *, timeout=90, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError('node readiness deadline exceeded')
        try:
            result = probe(min(3, remaining))
            if clock() >= deadline:
                raise TimeoutError('node readiness deadline exceeded')
            if result is True:
                return
        except urllib.error.HTTPError as error:
            # Only service-unavailable is a retryable readiness response.
            if error.code != 503:
                raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError('node readiness deadline exceeded')
        sleep(min(.25, remaining))


def assert_container_state(state):
    if (state.get('Running') is not True or state.get('OOMKilled') is not False
            or state.get('Health', {}).get('Status') != 'healthy'):
        raise RuntimeError('container is not running, healthy and free of OOM kill state')


def container_incarnation(info, *, stopped=False):
    """Require restart-disabled measurement runs; an OOM must remain observable."""
    if info.get('HostConfig', {}).get('RestartPolicy', {}).get('Name') not in ('no', ''):
        raise RuntimeError('measurement requires restart policy no (including observed containers)')
    state = info.get('State', {})
    if state.get('Running') is not (not stopped) or state.get('OOMKilled') is not False or state.get('ExitCode') != 0:
        raise RuntimeError('container running/termination state is not clean')
    count = info.get('RestartCount')
    started = info.get('State', {}).get('StartedAt')
    if type(count) is not int or count < 0 or not started or not info.get('Id'):
        raise RuntimeError('container incarnation metadata is incomplete')
    return {'id': info['Id'], 'restart_count': count, 'started_at': started}


def assert_incarnation(before, after, *, explicit_restart=False):
    if before['id'] != after['id'] or before['restart_count'] != after['restart_count']:
        raise RuntimeError('container replaced or unexpected automatic restart observed')
    changed = before['started_at'] != after['started_at']
    if changed != explicit_restart:
        raise RuntimeError('unexpected container incarnation change' if changed else 'explicit restart did not change incarnation')


def checked_restart(container, expected, inspect, evidence, command=None):
    """Preserve termination evidence before startup can reset Docker State.

    The runtime owner must exclude other lifecycle writers. This verifies clean
    termination, not the causal origin of a clean exit coincident with TERM.
    """
    if command is None:
        def command(argv, timeout):
            return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT, timeout=timeout)
    before = container_incarnation(inspect(container))
    assert_incarnation(expected, before)
    evidence['before'] = before
    # Unlike docker stop, kill fails on an already-stopped container. No forced
    # KILL fallback: a timeout is a failed run, not permission to erase evidence.
    command(['docker', 'kill', '--signal=TERM', container], 5)
    exit_code = command(['docker', 'wait', container], 60).strip()
    stopped = inspect(container)
    evidence['wait_exit_code'] = exit_code
    evidence['stopped_state'] = {key: stopped.get('State', {}).get(key)
                                 for key in ('Running', 'OOMKilled', 'ExitCode', 'StartedAt', 'FinishedAt')}
    stopped_identity = container_incarnation(stopped, stopped=True)
    assert_incarnation(before, stopped_identity)
    if exit_code != '0':
        raise RuntimeError('explicit termination did not exit cleanly')
    command(['docker', 'start', container], 15)
    after = container_incarnation(inspect(container))
    assert_incarnation(before, after, explicit_restart=True)
    evidence['after'] = after
    return after
