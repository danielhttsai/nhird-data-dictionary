import sys, io, time
sys.path.insert(0,'scripts')
import translate as T
cache=T.load_cache()
strings=T.collect_strings(None, max_len=None, include_long=True)
todo=[s for s in strings if T.sha(s) not in cache]
todo.sort(key=len)
print(f"remaining to translate: {len(todo)}", flush=True)
done=0
t0=time.time()
for i in range(0,len(todo),4):
    if time.time()-t0>520: print(f"time budget reached, did {done}", flush=True); break
    batch=todo[i:i+4]
    out=T.translate_batch(batch)
    for s,o in zip(batch,out):
        if o: cache[T.sha(s)]=o; done+=1
    T.save_cache(cache)
print(f"translated {done} this run; cache={len(cache)}", flush=True)
