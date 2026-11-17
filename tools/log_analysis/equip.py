from parse import *
EQ={'Lavaspur Boots','Dragonfire Blade','Leyline Axe','Basilisk Collar','Chainsaw','Skateboard'}
me='boros-dwarves'
RE_ATT=re.compile(r'^(.*) \((\d+)\) -  Attach to (.*) \((\d+)\)$')
dmg_by=collections.Counter(); dmg_eq=collections.Counter(); tot=0
tgt_status=collections.Counter(); tgt_name=collections.Counter(); phase=collections.Counter()
inresp=0; ntarget=0; equips=0; equips_on=collections.Counter()
deaths=collections.Counter()
for g,p in games():
    if me not in g['seats']: continue
    ms='Seat%d'%(g['seats'].index(me)+1); os_='Seat1' if ms=='Seat2' else 'Seat2'
    att={}  # equip id -> creature id
    names={}
    for t in parse(p):
        pending=0
        for e in t['ev']:
            if e[0]=='activated' and e[1]==ms and e[2] in EQ and e[3]: pending+=1; equips+=1; equips_on[e[3][0][0]]+=1
            elif e[0]=='res':
                m=RE_ATT.match(e[1])
                if m:
                    att[m.group(2)]=m.group(4); names[m.group(2)]=m.group(1); pending=max(0,pending-1)
                elif 'Thorin' in e[1] and 'attach' in e[1]:
                    pass
            elif e[0]=='die':
                for k in [k for k,v in att.items() if v==e[2]]: del att[k]
                if e[2] in att: del att[e[2]]
            elif e[0]=='dmg' and e[4] and e[5]==os_:
                eqs=tuple(sorted(names[k] for k,v in att.items() if v==e[2]))
                dmg_by[e[1]]+=e[3]; tot+=e[3]
                dmg_eq[eqs]+=e[3]
            if e[0] in ('cast','activated','triggered') and e[1]==os_ and e[3]:
                for nm,i in e[3]:
                    if nm in EQ: tgt_status['<equipment itself>']+=1
                    elif nm in ('Dwarven Mauler','Kíli the Resourceful',"Dáin's Company",'Dwalin, Weaponmaster','Thorin, Mountain-king','Dwarf Token'):
                        ntarget+=1; tgt_name[nm]+=1
                        eqs=tuple(sorted(names[k] for k,v in att.items() if v==i))
                        tgt_status[eqs]+=1
                        if pending: inresp+=1
                        phase[(('dw-turn' if t['active']==ms else 'opp-turn'),e[4])]+=1
print('combat dmg to opp by creature:',{k:round(v/tot,3) for k,v in dmg_by.most_common(8)},tot)
print('by equipment set:');[print('  ',k,v,round(v/tot,3)) for k,v in dmg_eq.most_common(15)]
print('equip activations',equips,equips_on.most_common())
print('opp targeted effects at dwarves creatures',ntarget,'while an equip was on the stack:',inresp)
print(tgt_name.most_common())
print('target status:');[print('  ',k,v) for k,v in tgt_status.most_common(15)]
print(phase.most_common(20))
