import json,collections,os
R=os.environ.get('MTGSIM_RUN','runs/rr-patched').rstrip('/')+'/'
G=[json.loads(l) for l in open(R+'games.jsonl')]
print(collections.Counter(g['status'] for g in G))
st=collections.defaultdict(lambda: collections.Counter())
for g in G:
    if g['winner_seat']<0: 
        for d in g['seats']: st[d]['draws']+=1
        continue
    for s,d in enumerate(g['seats']):
        w=g['winner_seat']==s; first=g['first_seat']==s
        c=st[d]; c['n']+=1; c['w']+=w
        c['n_play' if first else 'n_draw']+=1; c['w_play' if first else 'w_draw']+=w
        c['turns_w' if w else 'turns_l']+=g['turns']
        c['mull']+=g['players'][s]['mulligans']
        c['oppEndHand']+= sum(g['players'][1-s]['endHand'].values()) if w else 0
        c['seat0']+= s==0; c['w_seat0']+= w and s==0
for d,c in sorted(st.items(), key=lambda x:-x[1]['w']/x[1]['n']):
    print(f"{d:22s} n={c['n']} wr={c['w']/c['n']:.3f} play={c['w_play']/c['n_play']:.3f}({c['n_play']}) draw={c['w_draw']/c['n_draw']:.3f}({c['n_draw']}) turnsW={c['turns_w']/max(1,c['w']):.1f} turnsL={c['turns_l']/max(1,c['n']-c['w']):.1f} mull={c['mull']/c['n']:.2f} oppHandWhenWin={c['oppEndHand']/max(1,c['w']):.2f}")
# matchup rows for dwarves, dragons
for me in ['boros-dwarves','boros-dragons']:
    m=collections.defaultdict(lambda:[0,0,0,0,0,0])
    for g in G:
        if me in g['seats'] and g['winner_seat']>=0:
            s=g['seats'].index(me); o=g['seats'][1-s]; first=g['first_seat']==s
            r=m[o]; r[0]+=1; r[1]+=g['winner_seat']==s; r[2+ (0 if first else 2)]+=1; r[3+(0 if first else 2)]+=g['winner_seat']==s
    print(me)
    for o,r in sorted(m.items()): print(f"   vs {o:22s} {r[1]}/{r[0]}  play {r[3]}/{r[2]} draw {r[5]}/{r[4]}")
