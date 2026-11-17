import json,re,os,collections
R=os.environ.get('MTGSIM_RUN','runs/rr-patched').rstrip('/')+'/'
RE_TURN=re.compile(r'^Turn: Turn (\d+) \((Seat\d)\)')
RE_PHASE=re.compile(r"^Phase: (Seat\d)'s (.*)$")
RE_ATK=re.compile(r'^Combat: (Seat\d) assigned (.*) \((\d+)\) to attack (.*)\.$')
RE_BLK=re.compile(r'^Combat: (Seat\d) assigned (.*) \((\d+)\) to block (.*) \((\d+)\)\.$')
RE_NOBLK=re.compile(r"^Combat: (Seat\d) didn't block (.*) \((\d+)\)\.$")
RE_CAST=re.compile(r'^Add To Stack: (Seat\d) (cast|activated|triggered) (.*?)(?: targeting (.*))?$')
RE_LIFE=re.compile(r'^Life: Life: (Seat\d) (-?\d+) > (-?\d+)')
RE_DMG=re.compile(r'^Damage: (.*?) \((\d+)\) deals (\d+) (combat )?damage to (.*?)(?: \((\d+)\))?\.$')
RE_ZC=re.compile(r'^Zone Change: (.*) \((\d+)\) was put into (\w+) from Battlefield')
RE_MANA=re.compile(r'^Mana: (.*) \((\d+)\) - ')
RE_ATK2=re.compile(r'^(?:Combat: )?(Seat\d) assigned (.*) to attack (.*)\.$')
RE_BLK2=re.compile(r'^(?:Combat: )?(Seat\d) assigned (.*) to block (.*) \((\d+)\)\.$')
RE_NOBLK2=re.compile(r"^(?:Combat: )?(Seat\d) didn't block (.*) \((\d+)\)\.$")
RE_TGT2=re.compile(r'(?:^|, | and )(.+?) \((\d+)\)(?=$|, | and )')
RE_TGT3=re.compile(r'(.+?) \((\d+)\)(?:, |\]? ?$|\], \[|\] \[)')
RE_TGT=re.compile(r'([^\[\],]+?) \((\d+)\)')
def games():
    for l in open(R+'games.jsonl'):
        g=json.loads(l)
        p=R+'logs/games/%s__%s__%04d.log'%(g['a'],g['b'],g['game'])
        yield g,p
def parse(p):
    turns=[];cur=None
    for line in open(p,encoding='utf-8'):
        line=line.rstrip('\n')
        m=RE_TURN.match(line)
        if m:
            cur={'n':int(m.group(1)),'active':m.group(2),'ev':[],'phase':''}
            turns.append(cur);continue
        if cur is None: continue
        m=RE_PHASE.match(line)
        if m: cur['phase']=m.group(2);continue
        ph=cur['phase']
        m=RE_ATK2.match(line)
        if m:
            for nm,i in RE_TGT2.findall(m.group(2)): cur['ev'].append(('atk',m.group(1),nm,i,m.group(3)))
            continue
        m=RE_BLK2.match(line)
        if m:
            for nm,i in RE_TGT2.findall(m.group(2)): cur['ev'].append(('blk',m.group(1),nm,i,m.group(3),m.group(4)))
            continue
        m=RE_NOBLK2.match(line)
        if m: cur['ev'].append(('noblk',m.group(1),m.group(2),m.group(3)));continue
        m=RE_CAST.match(line)
        if m:
            t=RE_TGT3.findall(m.group(4).strip().strip('[]')) if m.group(4) else []
            raw=m.group(4) or ''
            cur['ev'].append((m.group(2),m.group(1),m.group(3),[(a.strip(),b) for a,b in t],ph,raw));continue
        m=RE_LIFE.match(line)
        if m: cur['ev'].append(('life',m.group(1),int(m.group(2)),int(m.group(3)),ph));continue
        m=RE_DMG.match(line)
        if m: cur['ev'].append(('dmg',m.group(1),m.group(2),int(m.group(3)),bool(m.group(4)),m.group(5),m.group(6)));continue
        m=RE_ZC.match(line)
        if m: cur['ev'].append(('die',m.group(1),m.group(2),m.group(3)));continue
        m=RE_MANA.match(line)
        if m: cur['ev'].append(('mana',m.group(1),m.group(2)));continue
        if line.startswith('Resolve Stack:'): cur['ev'].append(('res',line[15:],ph))
    return turns
