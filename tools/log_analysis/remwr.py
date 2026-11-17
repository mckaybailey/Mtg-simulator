from parse import *
import sys
for me in ['boros-dwarves','boros-dragons']:
    DW=set()
    for l in open(f'decks/standard/meta/{me}.txt'):
        l=l.strip()
        if l=='Sideboard': break
        if l and l[0].isdigit(): DW.add(l.split(' ',1)[1])
    DW|={'Dwarf Token'}
    C=collections.Counter(); D=collections.Counter()
    for g,p in games():
        if me not in g['seats'] or g['seats'][0]==g['seats'][1]: continue
        si=g['seats'].index(me); ms='Seat%d'%(si+1); os_='Seat1' if ms=='Seat2' else 'Seat2'
        n=0; deaths=0; cre=0
        for t in parse(p):
            for e in t['ev']:
                if e[0]=='cast' and e[1]==os_ and e[3] and any(nm in DW for nm,i in e[3]): n+=1
                if e[0]=='die' and e[1] in DW and e[1] not in ('Lavaspur Boots','Dragonfire Blade','Leyline Axe','Chainsaw','Skateboard','Basilisk Collar','Treasure Token') : deaths+=1
        w=g['winner_seat']==si
        k=min(n,4); C[k,'n']+=1; C[k,'w']+=w
        k=min(deaths,6); D[k,'n']+=1; D[k,'w']+=w
    print(me,'win rate by # opp SPELLS cast targeting its permanents:', {k:f"{C[k,'w']}/{C[k,'n']}" for k in range(5)})
    print(me,'win rate by # own creatures that left battlefield (died/exiled):', {k:f"{D[k,'w']}/{D[k,'n']}" for k in range(7)})
