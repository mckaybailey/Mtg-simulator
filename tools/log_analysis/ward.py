import re,glob,collections,os
R=os.environ.get('MTGSIM_RUN','runs/rr-patched').rstrip('/')+'/'
RE=re.compile(r'^Resolve Stack: Ward \{1\}.*\[Source: (.*) \((\d+)\), Target: (.*) \((\d+)\)\]')
res=collections.Counter(); bysrc=collections.defaultdict(collections.Counter); ex=[]
for p in sorted(glob.glob(R+'logs/games/*boros-dwarves*.log')):
    L=open(p,encoding='utf-8').read().split('\n')
    i=0
    while i<len(L):
        m=RE.match(L[i])
        if m:
            src,sid,tg,tid=m.groups()
            # count consecutive ward resolutions for same source/target
            n=1
            while RE.match(L[i+n] if i+n<len(L) else '') : n+=1
            # paid? look for Mana lines between the ward trigger add and this resolve: look back to "Add To Stack: SeatX triggered <tg>"
            j=i-1; mana=0
            while j>0 and not (L[j].startswith('Add To Stack:') and ' triggered '+tg in L[j]):
                j-=1
            # look forward for resolution of source
            ok=False
            for k in range(i+n,min(len(L),i+n+14)):
                if L[k].startswith('Turn:') : break
                if L[k].startswith('Resolve Stack:') and (('%s (%s) -'%(src,sid)) in L[k] or ('Targeting: [[%s (%s)'%(tg,tid)) in L[k] or ('%s (%s)'%(tg,tid) in L[k] and src in L[k])): ok=True;break
                if L[k].startswith('Damage: %s (%s) deals'%(src,sid)) and '%s (%s)'%(tg,tid) in L[k]: ok=True;break
            res[('resolved' if ok else 'COUNTERED',n)]+=1; bysrc[src]['resolved' if ok else 'COUNTERED']+=1
            if not ok and len(ex)<400: ex.append((p.split('/')[-1],i,src,tg))
            i+=n
        else: i+=1
print(res); 
for s,c in sorted(bysrc.items(),key=lambda x:-sum(x[1].values())): print(s,dict(c))
import random; random.seed(1)
for e in random.sample(ex,6): print(e)
