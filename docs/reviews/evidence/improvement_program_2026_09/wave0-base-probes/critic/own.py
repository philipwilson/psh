import json,re
inv=json.load(open('../judge/inventory.json'))
status={r['cid']:r['status'] for r in inv}; kind={r['cid']:r['kind'] for r in inv}; sev={r['cid']:r['severity'] for r in inv}
def ids(s): return re.findall(r'C\d{3}',s)
M={
'0':ids("C242, C241, C243, C238, C169, C245, C153, C181"),
'1':ids("C001, C032, C031, C043, C225, C074, C044, C033, C231, C010, C004, C005, C006, C011, C164, C170, C020, C040, C041, C042, C022, C082, C091, C081, C030, C098, C141, C027, C072, C028, C090, C093, C094, C095, C096, C136, C194, C226, C023, C024, C025, C026, C068, C179"),
'3':ids("C008, C100, C191, C013, C046, C102, C080, C002, C003, C007, C047, C009, C014, C221, C021, C059, C038, C126, C127, C092, C180"),
'4':ids("C015, C017, C052, C054, C110, C107, C016, C018, C166, C053, C173, C066, C069, C219, C139, C039, C051, C111, C055, C061, C118, C130, C079, C029, C076, C134, C135, C200, C075, C077, C078, C089, C070, C071, C195, C197, C198, C086, C157, C158, C161, C063, C065, C067, C124, C182, C183, C184, C185, C206, C207, C064, C056, C057, C058, C060, C062, C083, C084, C144, C085, C145, C147, C210, C099, C211, C235, C116, C117, C122, C177, C034, C156, C151, C155, C035, C036, C212, C152, C037, C213, C097, C174, C214"),
'5':ids("C012, C019, C048, C050, C103, C128, C073, C088, C209, C239, C240, C229"),
'R':ids("C167, C189, C192, C193, C215"),
'6':ids("C220, C222, C223, C224, C178, C227, C228, C230, C232, C233, C234, C236, C237, C244, C045, C049, C101, C104, C105, C113, C119, C121, C123, C125, C129, C131, C132, C133, C137, C138, C140, C142, C143, C146, C148, C149, C150, C154, C159, C160, C162, C176, C216, C201, C202, C217, C087, C106, C108, C109, C112, C115, C168, C175, C199, C203, C204, C205, C218, C187, C188"),
'Park':ids("C171, C172, C120, C165, C190, C196, C186"),
'Excl':ids("C114, C163, C208"),
}
from collections import Counter
c=Counter(); where={}
for w,l in M.items():
    for x in l: c[x]+=1; where.setdefault(x,[]).append(w)
allc={r['cid'] for r in inv}
print("total mapped distinct:",len(c),"sum:",sum(c.values()))
print("double-owned:",[(k,where[k]) for k,v in c.items() if v>1])
print("unowned:",sorted(allc-set(c)))
print("unknown:",sorted(set(c)-allc))
print("queued but fixed/not_repro:",[(x,status[x],where[x]) for x in c if status[x] in('fixed','not_reproducible') and where[x]!=['Excl']])
print("live not in wave:",[(x,where[x]) for x in c if status[x]=='live' and where[x][0] in('Park','Excl')])
print("Owned-in-wave n/a design rows (informational):",len([x for x in c if status[x]=='n/a' and where[x][0] not in('Park','Excl')]))
print("statuses:",Counter(status.values()))
# check §7-§13 'Owned findings' text vs §16 map? later
