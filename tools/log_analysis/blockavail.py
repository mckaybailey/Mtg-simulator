from board import *
S=collections.defaultdict(collections.Counter)
for g,p in games():
    T=walk(g,p)
    for i,r in enumerate(T):
        if not r['atk']: continue
        for key in [('A',r['deckA']),('D',r['deckD']),('AD',r['deckA'],r['deckD'])]:
            c=S[key]; c['atkturns']+=1; c['attackers']+=len(r['atk'])
            nb=sum(1 for e in r['atk'] if e[3] in r['blk'])
            c['blocked']+=nb
            if r['availD']>0:
                c['t_avail']+=1; c['att_avail']+=len(r['atk']); c['blk_avail']+=nb; c['t_anyblock']+= nb>0
                c['availsum']+=r['availD']
            lethal = r['lifeD1']<=0
            if lethal:
                c['lethal']+=1
                if r['availD']>0: c['lethal_avail']+=1; c['lethal_avail_noblock']+= nb==0
                # did defender attack on own previous turn?
                if i>0 and T[i-1]['A']==r['D'] and T[i-1]['atk']:
                    c['lethal_after_def_attacked']+=1
                    c['def_attackers_prev']+=len(T[i-1]['atk'])
                c['lethal_dmg']+=r['pdmg']; c['lethal_life']+=r['lifeD0']
def row(c):
    return (f"atkturns={c['atkturns']:4d} attackers={c['attackers']:4d} | turns w/ untapped (cast) blocker: {c['t_avail']/max(1,c['atkturns']):.2f}; in those: attackers blocked {c['blk_avail']}/{c['att_avail']}={c['blk_avail']/max(1,c['att_avail']):.3f}, turns w/ any block {c['t_anyblock']/max(1,c['t_avail']):.3f}"
            f" | lethal turns={c['lethal']} w/avail blocker={c['lethal_avail']} (no block {c['lethal_avail_noblock']}) afterDefAttacked={c['lethal_after_def_attacked']} avgDmg={c['lethal_dmg']/max(1,c['lethal']):.1f} avgLife={c['lethal_life']/max(1,c['lethal']):.1f}")
print('ATTACKER');[print(f"{k[1]:20s}",row(c)) for k,c in sorted(S.items()) if k[0]=='A']
print('DEFENDER');[print(f"{k[1]:20s}",row(c)) for k,c in sorted(S.items()) if k[0]=='D']
