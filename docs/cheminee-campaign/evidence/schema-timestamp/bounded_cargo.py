import argparse,datetime,json,os,pathlib,shutil,signal,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--log',required=True);p.add_argument('--status',required=True);p.add_argument('--minimum-free-mib',type=int,default=640);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
command=a.command[1:] if a.command[:1]==['--'] else a.command
start=datetime.datetime.now(datetime.timezone.utc).isoformat();minimum=a.minimum_free_mib*1048576
record={'command':command,'start_utc':start,'minimum_free_bytes':minimum,'stopped_for_disk_headroom':False,'samples':[]}
with open(a.log,'w') as log:
 child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 while child.poll() is None:
  free=shutil.disk_usage('/workspace').free
  record['samples'].append({'monotonic':time.monotonic(),'free_bytes':free})
  if free<minimum:
   record['stopped_for_disk_headroom']=True;os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=15)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL)
   break
  time.sleep(1)
 record['exit_code']=child.wait()
 record['free_bytes_after']=shutil.disk_usage('/workspace').free
pathlib.Path(a.status).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:v for k,v in record.items() if k!='samples'}));raise SystemExit(record['exit_code'])
