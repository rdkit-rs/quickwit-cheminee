#!/usr/bin/env python3
"""Bounded single-host searcher-loss probe over the retained synthetic fixture.
No ingestion, corruption, power-loss, replicated-storage or production HA claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

if not __debug__: raise SystemExit('assertions required')
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture-dir', type=Path, required=True)
p.add_argument('--binary', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a=p.parse_args()
if a.output.exists(): p.error('choose fresh output')
work=a.fixture_dir.resolve(); binary=a.binary.resolve()
pidfile=work/'continuation-fixed-pids.json'
pids=json.loads(pidfile.read_text()); assert len(pids)==3
leaf=pids[1]
owned=Path('/proc')/str(leaf)/'cmdline'
assert str(work/'leaf-a.json').encode() in owned.read_bytes(), 'refuse unrelated process'
config=json.loads((work/'leaf-a.json').read_text())
assert config['node_id']=='leaf-a' and config['listen_address']=='127.0.0.1'
base='http://127.0.0.1:19480'; http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
r={'scope':'16 synthetic rows; one host, shared local storage, searcher process SIGKILL; no production HA or durability claim',
   'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   'samples':[],'status':'running'}
def request(path,body=None):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
    try:
        with http.open(req,timeout=3) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
def nodes():
    code,data=request('/api/v1/cluster');assert code==200
    return sorted(n['node_id'] for n in data['ready_nodes'])
f=json.loads((work/'results.json').read_text())
graph=next(c['distributed_topk']['molecular_graph'] for c in f['checks'] if 'molecular_graph' in c.get('distributed_topk',{}))
all_ids=list(range(1,13))+list(range(101,105))
variants={
 'broad':({'molecular_graph':graph},all_ids),
 'selective':({'molecular_graph':dict(graph,candidates={'type':'range','field':'record_id','lower_bound':'Unbounded','upper_bound':{'Included':4}})},[1,2,3,4]),
 'empty':({'molecular_graph':dict(graph,candidates={'type':'term','field':'family','value':'absent'})},[]),
 'novel':({'molecular_graph':dict(graph,prepared_smiles='N')},[])}
def check(phase,name):
    query,expected=variants[name];start=time.monotonic()
    try:code,data=request('/api/v1/_elastic/composable-topk/_search?allow_partial_search_results=false',{'query':query,'size':20,'track_total_hits':True,'sort':[{'record_id':'asc'}]})
    except (OSError,ValueError) as error:code,data=0,{'transport_error':type(error).__name__}
    row={'phase':phase,'query_kind':name,'elapsed_seconds':time.monotonic()-start,'status':code}
    if code==200:
        assert data['hits']['total']=={'value':len(expected),'relation':'eq'},data
        assert [h['_source']['record_id'] for h in data['hits']['hits']]==expected,data
        assert data['_shards']['failed']==0 and data['timed_out'] is False and data.get('terminated_early') is not True,data
        row['server_took_ms']=data['took'];row['count']=len(expected)
    else:row['error_type']='http' if code else data['transport_error']
    memory={}
    for pid in pids:
        try:
            fields=dict(line.split(':',1) for line in (Path('/proc')/str(pid)/'status').read_text().splitlines() if ':' in line)
            memory[str(pid)]={'rss_kib':int(fields.get('VmRSS','0 kB').split()[0]),'hwm_kib':int(fields.get('VmHWM','0 kB').split()[0])}
        except FileNotFoundError:pass
    row['process_memory']=memory;r['samples'].append(row)
    return code==200
killed=False
try:
    assert nodes()==['leaf-a','leaf-b','root']
    for _ in range(5):
        for name in variants:assert check('before',name)
    os.kill(leaf,signal.SIGKILL);killed=True;r['kill_monotonic']=time.monotonic()
    deadline=time.monotonic()+60
    while True:
        ok=check('loss_transition','broad')
        ready=nodes()
        if ok and ready==['leaf-b','root']:break
        if time.monotonic()>deadline:raise TimeoutError('surviving searcher did not recover within60s')
        time.sleep(.2)
    r['survivor_ready_seconds']=time.monotonic()-r['kill_monotonic'];r['survivor_nodes']=ready
    for _ in range(5):
        for name in variants:assert check('survivor',name)
    r['status']='passed'
except BaseException as e:
    r['status']='failed';r['error']=type(e).__name__+': '+str(e)
    raise
finally:
    if killed:
        with (work/'leaf-a-loss-recovery.log').open('w') as log:
            child=subprocess.Popen([str(binary),'run','--config',str(work/'leaf-a.json'),'--service','searcher'],stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,QW_DISABLE_TELEMETRY='1'))
        pids[1]=child.pid;pidfile.write_text(json.dumps(pids)+'\n');r['restored_pid']=child.pid
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            if nodes()==['leaf-a','leaf-b','root']:break
            time.sleep(.2)
        else:r['status']='failed';r['recovery_error']='restarted searcher not ready within60s'
        if r['status']=='passed':
            for name in variants:
                if not check('restored',name):r['status']='failed'
    a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'status':r['status'],'samples':len(r['samples']),'survivor_ready_seconds':r.get('survivor_ready_seconds')}))
if r['status']!='passed':raise SystemExit(1)
