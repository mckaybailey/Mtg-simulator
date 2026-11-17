import collections,sys
from parse import *
# per (attacking deck, defending deck): attackers at player, blocked, unblocked, chump, attack turns, dmg
S=collections.defaultdict(collections.Counter)
for g,p in games():
    seatdeck={'Seat1':g['seats'][0],'Seat2':g['seats'][1]}
    for t in parse(p):
        A=seatdeck[t['active']]; D=seatdeck['Seat2' if t['active']=='Seat1' else 'Seat1']
        atk={};blk=collections.defaultdict(list);dead=set();unb=set()
        for e in t['ev']:
            if e[0]=='atk': atk[e[3]]=e
            elif e[0]=='blk': blk[e[5]].append(e[3])
            elif e[0]=='noblk': unb.add(e[3])
            elif e[0]=='die': dead.add(e[2])
        for k in [(A,D),(A,'*'),('*',D)]:
            c=S[k]
            c['turns']+=1
            if atk: c['atkturns']+=1
            for i,e in atk.items():
                c['attackers']+=1
                if i in blk:
                    c['blocked']+=1
                    bd=all(b in dead for b in blk[i]); ad=i in dead
                    if bd and not ad: c['chump']+=1
                    elif ad and not bd: c['blockwin']+=1
                    elif ad and bd: c['trade']+=1
                    else: c['bounce']+=1
                    if len(blk[i])>1: c['multiblock']+=1
            for e in t['ev']:
                if e[0]=='dmg' and e[4] and e[5].startswith('Seat'): c['pdmg']+=e[3]
import pickle
decks=sorted({k[0] for k in S if k[0]!='*'})
def row(k):
    c=S[k]; a=max(1,c['attackers']); b=max(1,c['blocked'])
    return f"atk/turn={c['attackers']/c['turns']:.2f} blocked={c['blocked']/a:.3f} [chump {c['chump']/b:.2f} atkdies {c['blockwin']/b:.2f} trade {c['trade']/b:.2f} bounce {c['bounce']/b:.2f}] dmg/turn={c['pdmg']/c['turns']:.2f} n_att={c['attackers']}"
print("== as ATTACKER (vs all)")
for d in decks: print(f"{d:22s}",row((d,'*')))
print("== as DEFENDER (vs all)")
for d in decks: print(f"{d:22s}",row(('*',d)))
for me in ['boros-dwarves','boros-dragons','mono-green-landfall']:
    print("==",me,"attacking each deck")
    for d in decks:
        if d!=me: print(f"  {d:22s}",row((me,d)))
print("== each deck attacking: vs dwarves | vs dragons | vs others (attackers per own turn, share of own creature... dmg/turn)")
for d in decks:
    o=collections.Counter()
    for k,c in S.items():
        if k[0]==d and k[1] not in ('*','boros-dwarves','boros-dragons',d):
            o.update(c)
    def f(c): return f"atk/turn={c['attackers']/max(1,c['turns']):.2f} atkturns%={c['atkturns']/max(1,c['turns']):.2f} dmg/turn={c['pdmg']/max(1,c['turns']):.2f} blocked={c['blocked']/max(1,c['attackers']):.2f}"
    print(f"{d:20s} DW[{f(S[(d,'boros-dwarves')])}] DR[{f(S[(d,'boros-dragons')])}] OTH[{f(o)}]")
