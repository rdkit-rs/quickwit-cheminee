#!/usr/bin/env python3
"""Cooperating campaign build admission, job inspection and emergency stopping.
Run inside the existing builder, from quickwit/. Never creates a container.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import shlex
import subprocess
import sys
import time

MIB = 1024 * 1024
ENV_KEYS = ('CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG', 'CARGO_INCREMENTAL',
            'CARGO_BUILD_JOBS', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_TARGET_DIR', 'CARGO_HOME', 'RUSTUP_TOOLCHAIN', 'CFLAGS', 'PKG_CONFIG_PATH', 'QW_KRB5_CRATE')


def write_state(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)


def identity(pid):
    try:
        text = (Path('/proc') / str(pid) / 'stat').read_text()
        fields = text[text.rfind(')') + 2:].split()
        return {'start_ticks': fields[19], 'state': fields[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def inspect_state(path):
    value = json.loads(path.read_text())
    if value.get('pid_namespace') != os.readlink('/proc/self/ns/pid'):
        value['inspection'] = 'different_pid_namespace; inspect inside original builder, do not restart'
    elif value.get('boot_id') != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        value['inspection'] = 'different boot; inspect saved outcome, do not infer a live PID'
    elif 'child_pid' in value:
        current = identity(value['child_pid'])
        value['child_alive'] = bool(current and current['start_ticks'] == value.get('child_start_ticks') and current['state'] != 'Z')
        value['group_members'] = group_members(value['child_pid'])
        value['inspection'] = 'surviving job/group; do not restart' if value['child_alive'] or value['group_members'] else 'no matching live child/group; inspect terminal status and log before retry'
    lock_path = value.get('lock_path')
    if lock_path:
        with Path(lock_path).open('r') as lock:
            value['global_lock_state_path'] = lock.read().strip()
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                value['global_heavy_lock_held'] = False
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except BlockingIOError:
                value['global_heavy_lock_held'] = True
                value['inspection'] = 'global heavy-phase lock held; inspect its active state, do not restart'
    return value


def group_members(group):
    members = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            text = (entry / 'stat').read_text()
            fields = text[text.rfind(')') + 2:].split()
            if int(fields[2]) == group and fields[0] != 'Z': members.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError): pass
    return members


def stop_group(group):
    if not group_members(group): return
    try: os.killpg(group, signal.SIGTERM)
    except ProcessLookupError: return
    deadline = time.monotonic() + 15
    while group_members(group) and time.monotonic() < deadline: time.sleep(.1)
    if group_members(group):
        try: os.killpg(group, signal.SIGKILL)
        except ProcessLookupError: return
        deadline = time.monotonic() + 5
        while group_members(group) and time.monotonic() < deadline: time.sleep(.1)
    if group_members(group): raise RuntimeError('process group cleanup incomplete')


def positive_integer(value, name):
    if type(value) is not int or value <= 0: raise ValueError(name + ' must be a positive integer')


def validate_policy(policy, phase):
    for key in ('reserve_mib', 'emergency_floor_mib'): positive_integer(policy[key], key)
    budget = phase.get('growth_budget_mib')
    if budget is not None: positive_integer(budget, 'growth_budget_mib')
    lower = phase.get('observed_growth_lower_bound_mib', 0)
    if type(lower) is not int or lower < 0: raise ValueError('growth lower bound must be a nonnegative integer')
    if phase.get('command'):
        positive_integer(phase.get('timeout_seconds'), 'timeout_seconds')
    if not isinstance(phase['command'], list) or any(not isinstance(x, str) or not x for x in phase['command']):
        raise ValueError('command must be a list of nonempty strings')


def unmanaged_builds():
    names = {'cargo', 'rustc', 'gcc', 'g++', 'clang', 'clang++', 'cc1', 'cc1plus', 'ld', 'ld.lld', 'make', 'cmake', 'ninja'}
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            name = (entry/'comm').read_text().strip()
            state = identity(int(entry.name))
            if name in names and state and state['state'] != 'Z': found.append({'pid':int(entry.name),'name':name})
        except (FileNotFoundError, ProcessLookupError): pass
    return found


def inspect_previous(lock, reviewed_digest):
    lock.seek(0)
    prior = lock.read().strip()
    if not prior: return
    path = Path(prior)
    if not path.is_file():
        raise ValueError('prior state is missing; explicit operator review/recovery of lock and original job required: ' + str(path))
    value = json.loads(path.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    reviewed = reviewed_digest == digest
    terminal = {'completed', 'process_failed', 'stopped_for_disk', 'timed_out', 'interrupted',
                'orphaned_child_processes', 'stopped_for_growth_budget', 'refused_uncalibrated', 'refused_budget',
                'refused_headroom', 'refused_dependency',
                'admitted_dry_run; dependency checks and command not executed'}
    if 'child_pid' in value:
        if type(value['child_pid']) is not int or value['child_pid'] <= 0:
            raise ValueError('invalid previous child identity; inspect saved record')
        same_boot = value.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        same_namespace = value.get('pid_namespace') == os.readlink('/proc/self/ns/pid')
        if not same_boot or not same_namespace:
            if reviewed and value.get('status') in terminal: return
            raise ValueError('previous child boot/namespace differs; inspect original container; only a reviewed terminal state can be reused')
        if group_members(value['child_pid']):
            raise ValueError('previous process group survives; do not restart')
    if value.get('status') not in terminal or not value.get('boot_id') or not value.get('pid_namespace'):
        if not reviewed:
            raise ValueError('prior job lacks reliable terminal state; inspect log and pass reviewed state SHA256 only after review: ' + digest)


def check_preflight(path, cwd):
    if path is None:
        raise ValueError('workspace preflight report required')
    report = json.loads(path.read_text())
    unsupported=[k for k in os.environ if ('PKG_CONFIG' in k and k!='PKG_CONFIG_PATH') or 'TENSORFLOW' in k or k.startswith('TF_RUST_') or k=='CARGO_BUILD_TARGET']
    if unsupported: raise ValueError('unsupported dependency overrides: '+','.join(sorted(unsupported)))
    if report.get('status') != 'passed':
        raise ValueError('workspace dependency preflight did not pass')
    if report.get('cwd') != str(cwd):
        raise ValueError('preflight workspace differs')
    age = time.time() - report.get('created_unix', 0)
    if not 0 <= age <= 3600:
        raise ValueError('preflight older than one hour; refresh cheap checks')
    required = [cwd/'Cargo.lock', cwd/'scripts/ci/with-krb5-c23.sh', cwd/'scripts/ci/krb5-c23.patch', Path(report['kerberos_crate']), Path(report['tensorflow_pc']), Path(report['pkg_config_executable']), *[Path(x) for x in report['tensorflow_libraries']]]
    if len(set(report['tensorflow_libraries'])) != 2 or not all(str(p) in report['file_hashes'] for p in required):
        raise ValueError('preflight lacks required dependency hashes')
    for name, digest in report['file_hashes'].items():
        with Path(name).open('rb') as stream: actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError('preflight input changed: ' + name)
    if str(Path(shutil.which('pkg-config')).resolve()) != report['pkg_config_executable']:
        raise ValueError('pkg-config executable changed')
    selected_pc = (Path(subprocess.check_output(['pkg-config', '--variable=pcfiledir', 'tensorflow'], text=True, timeout=5).strip()) / 'tensorflow.pc').resolve(strict=True)
    version = subprocess.check_output(['pkg-config', '--modversion', 'tensorflow'], text=True, timeout=5).strip()
    if str(selected_pc) != report['tensorflow_pc'] or version != report['tensorflow_version']:
        raise ValueError('TensorFlow metadata selection changed')
    flags=shlex.split(subprocess.check_output(['pkg-config','--libs','tensorflow'],text=True,timeout=5))
    if flags != report['tensorflow_link_flags']:
        raise ValueError('TensorFlow linker selection changed')
    if not all(str(Path(link).resolve(strict=True))==target for link,target in report['tensorflow_link_paths'].items()):
        raise ValueError('TensorFlow library symlink target changed')
    if Path(os.environ['QW_KRB5_CRATE']).resolve() != Path(report['kerberos_crate']):
        raise ValueError('Kerberos crate selection changed')
    if report['environment'] != {key: os.environ.get(key) for key in ('PKG_CONFIG_PATH', 'QW_KRB5_CRATE')}:
        raise ValueError('preflight dependency environment changed')


def validate_paths(args, lock_path):
    temporary = args.state.with_name(args.state.name + '.tmp')
    paths = [args.state, args.log, temporary, lock_path, args.policy]
    if args.preflight is not None: paths.append(args.preflight)
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError('state, log, temporary, lock, policy and preflight paths must be distinct')
    if any(p.exists() or p.is_symlink() for p in (args.state, args.log, temporary)):
        raise ValueError('fresh state, log and temporary paths required')


def filesystem_paths(filesystem, phase):
    """Conservatively require all build storage on the admitted device."""
    cwd = Path.cwd().resolve()
    target = Path(os.environ.get('CARGO_TARGET_DIR', cwd / 'target')).resolve()
    if phase.get('requires_preflight') or (cwd / 'Cargo.toml').is_file():
        # Cargo applies workspace/config target-dir overrides; do not guess them.
        metadata = json.loads(subprocess.check_output(
            ['cargo', 'metadata', '--offline', '--locked', '--no-deps', '--format-version', '1'],
            text=True, timeout=30))
        target = Path(metadata['target_directory']).resolve()
    paths = {'admitted': filesystem.resolve(strict=True), 'cwd': cwd,
             'cargo_target': target,
             'cargo_home': Path(os.environ.get('CARGO_HOME', Path.home() / '.cargo')).resolve()}
    admitted_device = paths['admitted'].stat().st_dev
    records = {}
    for label, path in paths.items():
        ancestor = path
        while not ancestor.exists(): ancestor = ancestor.parent
        device = ancestor.stat().st_dev
        records[label] = {'path': str(path), 'existing_ancestor': str(ancestor), 'device': device}
        if device != admitted_device:
            raise ValueError(label + ' is on a different device; require separate measured admission before running')
    return records


def disk_stop_reason(state, free):
    if free < state['emergency_floor_bytes']: return 'stopped_for_disk'
    if state['initial_free_bytes'] - free > state['growth_budget_mib'] * MIB:
        return 'stopped_for_growth_budget'
    return None


def run(args):
    policy = json.loads(args.policy.read_text())
    phase = policy['phases'][args.phase]
    validate_policy(policy, phase)
    validate_paths(args, Path(policy['lock_path']))
    args.state.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(policy['lock_path'])
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'refused_busy', 'reason': 'another cooperating heavy phase holds the lock; inspect its state, do not restart'}))
            return 3
        validate_paths(args, lock_path)
        lock.seek(0)
        previous_state_path = lock.read().strip() or None
        inspect_previous(lock, args.reviewed_prior_state_sha256)
        if unmanaged_builds():
            raise ValueError('existing compiler/build processes found; inspect surviving jobs before retry')
        storage = filesystem_paths(args.filesystem, phase)
        free = shutil.disk_usage(args.filesystem).free
        budget = phase.get('growth_budget_mib')
        reserve = policy['reserve_mib'] * MIB
        floor = policy['emergency_floor_mib'] * MIB
        if reserve < floor or floor <= 0:
            raise ValueError('reserve must cover a positive emergency floor')
        state = {'phase': args.phase, 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'pid_namespace': os.readlink('/proc/self/ns/pid'), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                 'previous_state_path': previous_state_path, 'reviewed_prior_state_sha256': args.reviewed_prior_state_sha256,
                 'runner_pid': os.getpid(), 'runner_start_ticks': identity(os.getpid())['start_ticks'],
                 'cwd': str(Path.cwd()), 'lock_path': str(lock_path.resolve()), 'policy_sha256': hashlib.sha256(args.policy.read_bytes()).hexdigest(),
                 'command': phase['command'], 'environment': {k: os.environ.get(k) for k in ENV_KEYS},
                 'initial_free_bytes': free, 'reserve_bytes': reserve, 'emergency_floor_bytes': floor,
                 'storage_paths': storage, 'growth_budget_mib': budget, 'samples': [], 'status': 'checking_admission'}
        # Persist the intent before publishing its pointer. A crash can leave an
        # unreferenced intent, never a lock pointing at an unwritten record.
        write_state(args.state, state)
        lock.seek(0); lock.truncate(); lock.write(str(args.state.resolve()) + '\n'); lock.flush()
        os.fsync(lock.fileno())
        if budget is None or not phase['command']:
            state.update(status='refused_uncalibrated', reason='no approved phase budget/command; do not create/export images by default')
        elif budget <= phase.get('observed_growth_lower_bound_mib', 0):
            state.update(status='refused_budget', reason='allowance must exceed observed failed-run lower bound')
        elif free < budget * MIB + reserve:
            state.update(status='refused_headroom', required_free_bytes=budget * MIB + reserve)
        elif args.admit_only:
            state['status'] = 'admitted_dry_run; dependency checks and command not executed'
        else:
            try:
                if phase.get('requires_preflight'):
                    check_preflight(args.preflight, Path.cwd())
                    if os.environ.get('CFLAGS') != '-std=gnu17':
                        raise ValueError('workspace recipe requires CFLAGS=-std=gnu17')
            except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
                state.update(status='refused_dependency', reason=str(error))
            else:
                return execute(args, phase, state, lock)
        write_state(args.state, state)
        print(json.dumps({k: state[k] for k in ('status', 'initial_free_bytes', 'growth_budget_mib', 'reserve_bytes')}))
        return 0 if args.admit_only and state['status'].startswith('admitted') else 2


def execute(args, phase, state, lock):
    interrupted = []
    previous = {s: signal.signal(s, lambda signum, frame: interrupted.append(signum)) for s in (signal.SIGTERM, signal.SIGINT)}
    child = None
    start = time.monotonic()
    stop_reason = None
    try:
        with args.log.open('x') as output:
            # Child inherits the lock: if the supervisor disappears while Cargo survives,
            # another cooperating runner cannot start a duplicate heavy job.
            state['status'] = 'launching'
            write_state(args.state, state)
            child = subprocess.Popen(phase['command'], stdout=output, stderr=subprocess.STDOUT,
                                     start_new_session=True, pass_fds=(lock.fileno(),))
            ident = identity(child.pid)
            state.update(status='running', child_pid=child.pid, child_start_ticks=ident['start_ticks'] if ident else None)
            write_state(args.state, state)
            last_checkpoint = time.monotonic()
            while child.poll() is None:
                free = shutil.disk_usage(args.filesystem).free
                state['samples'].append({'elapsed_seconds': time.monotonic()-start, 'free_bytes': free})
                if time.monotonic() - last_checkpoint >= 5:
                    write_state(args.state, state)
                    last_checkpoint = time.monotonic()
                if interrupted: stop_reason = 'interrupted'
                elif disk_stop_reason(state, free): stop_reason = disk_stop_reason(state, free)
                elif time.monotonic()-start > phase.get('timeout_seconds', 1800): stop_reason = 'timed_out'
                if stop_reason:
                    stop_group(child.pid)
                    child.wait()
                    break
                time.sleep(.5)
            code = child.wait()
            if group_members(child.pid):
                stop_reason = stop_reason or 'orphaned_child_processes'
                stop_group(child.pid)
            state.update(exit_code=code, status=stop_reason or ('completed' if code == 0 else 'process_failed'))
    except Exception as error:
        state.update(status='supervisor_error', error_type=type(error).__name__)
        if child is not None:
            try: stop_group(child.pid); child.wait()
            except Exception as cleanup: state['cleanup_error_type'] = type(cleanup).__name__
    finally:
        for signum, handler in previous.items(): signal.signal(signum, handler)
        final = shutil.disk_usage(args.filesystem).free
        if state.get('status') == 'completed' and disk_stop_reason(state, final):
            state['status'] = disk_stop_reason(state, final)
        state.update(final_free_bytes=final, elapsed_seconds=time.monotonic()-start)
        state['minimum_observed_free_bytes'] = min([state['initial_free_bytes'], final] + [s['free_bytes'] for s in state['samples']])
        state['maximum_observed_drawdown_bytes'] = state['initial_free_bytes'] - state['minimum_observed_free_bytes']
        state['measurement_note'] = 'filesystem-wide samples; subsecond peaks may be missed; unrelated writes are not isolated'
        write_state(args.state, state)
    print(json.dumps({k: state[k] for k in ('status', 'minimum_observed_free_bytes', 'maximum_observed_drawdown_bytes')}))
    return 0 if state['status'] == 'completed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    status = sub.add_parser('status'); status.add_argument('--state', type=Path, required=True)
    runner = sub.add_parser('run')
    runner.add_argument('--phase', required=True)
    runner.add_argument('--policy', type=Path, default=Path(__file__).with_name('campaign_phase_policy.json'))
    runner.add_argument('--filesystem', type=Path, default=Path('/workspace'))
    runner.add_argument('--state', type=Path, required=True)
    runner.add_argument('--log', type=Path, required=True)
    runner.add_argument('--preflight', type=Path)
    runner.add_argument('--admit-only', action='store_true')
    runner.add_argument('--reviewed-prior-state-sha256')
    args = parser.parse_args()
    if args.action == 'status': print(json.dumps(inspect_state(args.state), indent=2)); return 0
    try: return run(args)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({'status': 'configuration_error', 'error_type': type(error).__name__, 'reason': str(error)})); return 2


if __name__ == '__main__': sys.exit(main())
