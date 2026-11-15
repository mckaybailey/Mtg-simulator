from parse import *
import sys
me=sys.argv[1]
DW=set()
for l in open(f'decks/standard/meta/{me}.txt'):
    l=l.strip()
    if l=='Sideboard': break
    if l and l[0].isdigit(): DW.add(l.split(' ',1)[1])
DW|={'Dwarf Token','Dragon Token','Warrior Token','Treasure Token'}
C=collections.Counter();per=collections.defaultdict(collections.Counter);ng=collections.Counter()
endhand=collections.defaultdict(collections.Counter)
for g,p in games():
    if me not in g['seats'] or g['seats'][0]==g['seats'][1]: continue
    ms='Seat%d'%(g['seats'].index(me)+1); os_='Seat1' if ms=='Seat2' else 'Seat2'
    od=g['seats'][1-g['seats'].index(me)]; ng[od]+=1
    opp=g['players'][1-g['seats'].index(me)]
    lost = g['winner_seat']==g['seats'].index(me)
    for n,k in opp['endHand'].items():
        if lost: endhand[od][n]+=k
    endhand[od]['__lost']+=lost
    for t in parse(p):
        for e in t['ev']:
            if e[0] in('cast','activated','triggered') and e[1]==os_ and e[3]:
                for nm,i in e[3]:
                    if nm in DW:
                        per[od][(e[0],e[2][:40],nm, 'oppturn' if t['active']==ms else 'ownturn')]+=1
for od in sorted(per):
    print('==',od,'games',ng[od])
    agg=collections.Counter()
    for (k,sp,nm,w),v in per[od].items(): agg[(k,sp)]+=v
    for (k,sp),v in agg.most_common(12):
        tg=collections.Counter(); tm=collections.Counter()
        for (k2,sp2,nm,w),v2 in per[od].items():
            if (k2,sp2)==(k,sp): tg[nm]+=v2; tm[w]+=v2
        print(f"   {k:9s} {sp:40s} {v:4d} ({v/ng[od]:.2f}/g) {dict(tm)} {dict(tg.most_common(6))}")
    eh=endhand[od]; L=eh.pop('__lost')
    print('   opp end hand in its losses (n=%d):'%L, {k:round(v/max(1,L),2) for k,v in eh.most_common(8)})
