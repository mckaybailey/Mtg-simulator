import collections
from parse import *
RE_CRE=re.compile(r'^(.*) - Creature (-?\d+) / (-?\d+)$')
def other(s): return 'Seat2' if s=='Seat1' else 'Seat1'
def walk(g,p):
    """yield per turn: dict with board info before combat"""
    seatdeck={'Seat1':g['seats'][0],'Seat2':g['seats'][1]}
    alive={'Seat1':collections.Counter(),'Seat2':collections.Counter()}
    pt={}
    idseat={}; idname={}
    tapped={'Seat1':collections.Counter(),'Seat2':collections.Counter()}
    life={'Seat1':20,'Seat2':20}
    lastcast={}
    out=[]
    for t in parse(p):
        A=t['active'];D=other(A)
        tapped[A]=collections.Counter()  # untap
        rec={'n':t['n'],'A':A,'D':D,'deckA':seatdeck[A],'deckD':seatdeck[D],'lifeA0':life[A],'lifeD0':life[D],
             'atk':[],'blk':collections.defaultdict(list),'dead':set(),'pdmg':0,'ev':t['ev'],'availD':None,'aliveD':None,'aliveA':None}
        for e in t['ev']:
            k=e[0]
            if k=='cast': lastcast[e[2]]=e[1]
            elif k=='res':
                m=RE_CRE.match(e[1])
                if m:
                    s=lastcast.get(m.group(1))
                    if s: alive[s][m.group(1)]+=1; pt[m.group(1)]=(int(m.group(2)),int(m.group(3)))
            elif k=='mana':
                nm=e[1]
                for s in (A,D):
                    if alive[s][nm]>tapped[s][nm] and nm in pt: tapped[s][nm]+=1;break
            elif k=='atk':
                if rec['availD'] is None:
                    rec['availD']=sum(max(0,alive[D][n]-tapped[D][n]) for n in alive[D])
                    rec['aliveD']=+alive[D]; rec['aliveA']=+alive[A]; rec['tappedD']=+tapped[D]
                idseat[e[3]]=A; idname[e[3]]=e[2]
                if e[4].startswith('Seat'): rec['atk'].append(e)
                tapped[A][e[2]]+=1
            elif k=='blk':
                idseat[e[3]]=D; rec['blk'][e[5]].append(e)
            elif k=='die':
                nm,i=e[1],e[2]; rec['dead'].add(i)
                s=idseat.get(i)
                if s is None:
                    c=[x for x in ('Seat1','Seat2') if alive[x][nm]>0]
                    s=c[0] if len(c)==1 else None
                if s and alive[s][nm]>0:
                    alive[s][nm]-=1
                    if tapped[s][nm]>alive[s][nm]: tapped[s][nm]=alive[s][nm]
            elif k=='life': life[e[1]]=e[3]
            elif k=='dmg' and e[4] and e[5]==D: rec['pdmg']+=e[3]
        rec['lifeA1']=life[A];rec['lifeD1']=life[D]
        out.append(rec)
    return out
