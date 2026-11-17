from board import *
EQ={'Lavaspur Boots','Dragonfire Blade','Leyline Axe','Basilisk Collar','Chainsaw','Skateboard'}
for me in ['boros-dwarves','boros-dragons','mono-green-landfall','orzhov-lifegain','dimir-midrange']:
    c=collections.Counter(); ex=[]
    for g,p in games():
        if me not in g['seats']: continue
        T=walk(g,p)
        for i,r in enumerate(T):
            if r['deckA']!=me or r['lifeD1']>0 or not r['atk']: continue
            c['lethal']+=1
            over=-r['lifeD1']
            castnow={e[2] for e in r['ev'] if e[0]=='cast' and e[1]==r['A']}
            eqold=[e for e in r['ev'] if e[0]=='activated' and e[1]==r['A'] and e[2] in EQ and e[2] not in castnow]
            eqnew=[e for e in r['ev'] if e[0]=='activated' and e[1]==r['A'] and e[2] in EQ and e[2] in castnow]
            thorin=any(e[0]=='cast' and 'Thorin' in e[2] for e in r['ev'])
            newcre=[e for e in r['ev'] if e[0]=='res' and ' - Creature' in e[1]]
            prev=T[i-1] if i>0 else None
            datt=len(prev['atk']) if prev and prev['A']==r['D'] else 0
            if eqold: c['lethal turn used equip of equipment already on battlefield']+=1
            if eqnew or thorin: c['lethal turn used newly cast equipment/Thorin']+=1
            if datt:
                c['defender attacked prev turn']+=1
                if over<=2: c['  ..and overkill<=2']+=1
                if over<=4: c['  ..and overkill<=4']+=1
                if eqold: c['  ..and old equipment re-equipped']+=1; ex.append(('%s__%s__%04d'%(g['a'],g['b'],g['game']),r['n'],over,datt))
                # was defender's life before lethal turn > damage predicted from prior turn's damage?
            if r['availD']>0: c['defender had untapped cast creature']+=1
            if not r['blk']: c['no blocks at all']+=1
            c['sum overkill']+=over; c['sumdmg']+=r['pdmg']; c['sumlife']+=r['lifeD0']
            # prior Dwarves attack turn damage
            pd=[x['pdmg'] for x in T[:i] if x['deckA']==me and x['A']==r['A']]
            last=pd[-1] if pd else 0
            c['sum prev-turn dmg']+=last
            if r['pdmg']>=2*max(1,last) and r['pdmg']-last>=4: c['lethal dmg >= 2x previous turn dmg (burst)']+=1
    n=c['lethal']
    print('==',me); 
    for k,v in c.items(): print(f"   {k:60s} {v:5d} {v/n:.2f}")
    if me=='boros-dwarves': print(ex[:12])
