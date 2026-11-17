import json,collections,os
R=os.environ.get('MTGSIM_RUN','runs/rr-patched').rstrip('/')+'/'
S=collections.defaultdict(collections.Counter)
for l in open(R+'games.jsonl'):
    g=json.loads(l)
    for s in (0,1):
        P=g['players'][s]; opp=g['seats'][1-s]; me=g['seats'][s]
        grp='vsDwarves' if opp=='boros-dwarves' else 'vsDragons' if opp=='boros-dragons' else 'vsOther'
        for k in [(me,grp),('ALL',grp)]:
            c=S[k]; c['g']+=1
            for n,r in P['roles'].items():
                if 'removal' in r or 'sweeper' in r:
                    seen=P['opening'].get(n,0)+P['drawn'].get(n,0)
                    c['seen']+=seen; c['played']+=P['played'].get(n,0); c['end']+=P['endHand'].get(n,0)
                    c['idleOwn']+=P['idleOwn'].get(n,0); c['idleOpp']+=P['idleOpp'].get(n,0)
            for n,r in P['removal'].items():
                c['rcasts']+=r['casts']; c['poor']+=r['poor']; c['q']+=r['quality']
for k in sorted(S):
    c=S[k]
    if c['seen']<20: continue
    print(f"{k[0]:20s} {k[1]:10s} g={c['g']:4d} removal seen/g={c['seen']/c['g']:.2f} cast%={c['played']/max(1,c['seen']):.2f} endHand%={c['end']/max(1,c['seen']):.2f} idleOwnTurns/g={c['idleOwn']/c['g']:.2f} idleOppTurns/g={c['idleOpp']/c['g']:.2f} quality={c['q']/max(1,c['rcasts']):.2f}")
