"""Isolated synthetic dataset; never opens the clinic profile."""
import json
import platform
import statistics
import tempfile
import time
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clinic.storage import Store
from clinic.service import Service
from clinic.domain import today

with tempfile.TemporaryDirectory(prefix='faramarz-benchmark-') as folder:
    s=Store(folder);svc=Service(s);svc.register('synthetic','Benchmark-only-password');svc.login('synthetic','Benchmark-only-password')
    with s.db:
        s.db.executemany('INSERT INTO patients(name,phone,created) VALUES(?,?,?)',[(f'Synthetic patient {i:05}',f'+9370{i:07}',today()) for i in range(10000)])
    samples={}
    for term in ['Synthetic patient 099','+937000099','P-009999','not found']:
        timings=[]
        for _ in range(100):
            start=time.perf_counter();svc.search(term);timings.append((time.perf_counter()-start)*1000)
        samples[term]={'median_ms':round(statistics.median(timings),3),'p95_ms':round(sorted(timings)[94],3),'max_ms':round(max(timings),3)}
    cpu='unknown'
    if Path('/proc/cpuinfo').exists():
        cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),cpu)
    result={'platform':platform.platform(),'python':platform.python_version(),'cpu':cpu,'logical_cpus':os.cpu_count(),'dataset_patients':10000,'queries_each':100,'search':samples,'limitations':'Warm queries in a temporary profile on this development host; not a clinic laptop benchmark.'}
    print(json.dumps(result,indent=2));s.db.close()
