"""Bounded readiness checks; never retries writes or query correctness failures."""
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


def container_incarnation(info):
    """Require restart-disabled measurement runs; an OOM must remain observable."""
    if info.get('HostConfig', {}).get('RestartPolicy', {}).get('Name') not in ('no', ''):
        raise RuntimeError('measurement requires restart policy no (including observed containers)')
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
