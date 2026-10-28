"""Linux packaged first-account-screen timing, including process startup/imports."""
import json
import os
import select
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

binary=str(Path(sys.argv[1]).resolve());results=[];qt_platform=sys.argv[2] if len(sys.argv)>2 else 'offscreen'
with tempfile.TemporaryDirectory(prefix='faramarz-startup-') as folder:
    for trial in range(5):
        env=dict(os.environ,FARAMARZ_PROFILE=str(Path(folder)/str(trial)),QT_QPA_PLATFORM=qt_platform)
        began=time.perf_counter()
        p=subprocess.Popen(['unshare','-Urn',binary],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        try:
            ready,_,_=select.select([p.stdout],[],[],20)
            if not ready:raise RuntimeError('Account screen did not become ready')
            line=p.stdout.readline().strip()
            if not line.startswith('Account screen:'):raise RuntimeError(line or 'No startup marker')
            elapsed=time.perf_counter()-began
            rss=next((line.split(':',1)[1].strip() for line in Path(f'/proc/{p.pid}/status').read_text().splitlines() if line.startswith('VmRSS:')),'unknown')
            results.append(dict(trial=trial+1,wall_seconds=round(elapsed,3),resident_memory=rss))
        finally:
            p.terminate();p.wait(timeout=10)
print(json.dumps({'binary':binary,'network':'isolated user/network namespace, no network interfaces enabled','profile':'Fresh empty profile per trial; no human authentication time','platform':qt_platform+' Qt rendering on Ubuntu 24.04; warm OS disk cache after build','trials':results,'median_seconds':round(statistics.median(r['wall_seconds'] for r in results),3)},indent=2))
