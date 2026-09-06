import json, re, collections
P='/private/tmp/claude-501/-Users-pwilson-src-psh/21ae5f2e-9275-435c-b935-81973d58614e/scratchpad/program_v2.md'
inv=json.load(open('/private/tmp/claude-501/-Users-pwilson-src-psh/21ae5f2e-9275-435c-b935-81973d58614e/scratchpad/inventory.json'))
doc=open(P).read()
lines=doc.split('\n')
# locate §16 table
s=doc.index('## 16. Finding ownership map'); e=doc.index('## 17. Risk register')
sec=doc[s:e]
rows=[l for l in sec.split('\n') if l.startswith('| ') and not l.startswith('| Wave') and not l.startswith('|---')]
owner=collections.defaultdict(list)
for r in rows:
    cells=[c.strip() for c in r.strip('|').split('|')]
    w=cells[0]
    for c in re.findall(r'C\d{3}', cells[1]):
        owner[c].append(w)
print('rows in §16:', len(rows))
mapped=set(owner)
print('distinct cids mapped:', len(mapped), 'sum of mentions:', sum(len(v) for v in owner.values()))
dbl={c:v for c,v in owner.items() if len(v)>1}
print('double-owned:', dbl)
inv_by={x['cid']:x for x in inv}
print('inventory size', len(inv), 'statuses', collections.Counter(x['status'] for x in inv))
unknown=[c for c in mapped if c not in inv_by]
print('unknown cids in map:', unknown)
need=[x['cid'] for x in inv if x['status'] in ('live','oracle_changed')]
missing=[c for c in need if c not in mapped]
print('live/oracle_changed count', len(need), 'missing from map:', missing)
multi=[c for c in need if len(owner.get(c,[]))!=1]
print('live/oracle_changed not exactly once:', multi)
bad=[c for c in mapped if inv_by[c]['status'] in ('fixed','not_reproducible') and owner[c]!=['Excluded']]
print('fixed/not_repro queued outside Excluded:', bad)
excl=[c for c in mapped if owner[c]==['Excluded']]
print('Excluded rows:', excl, [inv_by[c]['status'] for c in excl])
# statuses other than live/oracle_changed/fixed/not_reproducible
other=[(x['cid'],x['status'],owner.get(x['cid'])) for x in inv if x['status'] not in ('live','oracle_changed','fixed','not_reproducible')]
print('other statuses:', other)
# Park rows status
for c in ['C171','C172','C120','C165','C190','C196','C186']:
    print(c, inv_by[c]['status'], inv_by[c]['kind'], owner[c])
# oracle_changed
print('oracle_changed:', [(x['cid'],owner.get(x['cid'])) for x in inv if x['status']=='oracle_changed'])
# cids in inventory not in map at all
notmapped=[x['cid'] for x in inv if x['cid'] not in mapped]
print('inventory cids absent from map:', notmapped)
# --- W0-N routing: find each W0-N in §6 with "→ slot X" or "→ X"
s6=doc.index('## 6. Wave 0'); e6=doc.index('## 7. Wave 1')
sec6=doc[s6:e6]
# slot headings in §7-§10
heads=re.findall(r'\*\*(\d\.\d+[ab]?) ', doc)
heads=set(heads)
print('slot headings found:', sorted(heads, key=lambda x:(int(x.split('.')[0]), float(x.split('.')[1].rstrip('ab')))))
for n in range(1,8):
    tag=f'W0-N{n}'
    ms=re.findall(r'\*\*W0-N%d\*\*[^→]*?→ (?:slot )?(\d\.\d+)'%n, sec6)
    print(tag, 'routes in §6:', ms, 'heading exists:', [m in heads for m in ms])
    # confirm slot brief mentions tag
    for m in ms:
        pat=re.compile(r'\*\*%s [^\n]*'%re.escape(m))
        h=pat.search(doc)
        print('   slot',m,'heading mentions',tag,':', bool(h) and (tag in h.group(0)))
