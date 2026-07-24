import os, sys, pty, time, select
sys.path.insert(0, '/Users/pwilson/src/psh-r22-verify')

def drive(argv, env):
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(argv[0], argv, env)
    time.sleep(0.8)
    os.write(fd, b'echo \\<<EOF\n')   # the target line
    time.sleep(0.8)
    out = b''
    # drain
    while True:
        r, _, _ = select.select([fd], [], [], 0.4)
        if not r:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    try:
        os.write(fd, b'ZZDONE\n')     # a marker line; heredoc body if pending
        time.sleep(0.5)
        while True:
            r, _, _ = select.select([fd], [], [], 0.4)
            if not r:
                break
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    try:
        os.write(fd, b'EOF\nexit\n')
        time.sleep(0.4)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
    return out

env = dict(os.environ)
env['PS1'] = 'P1> '
env['PS2'] = 'P2> '
env['TERM'] = 'dumb'

print("############ BASH interactive ############")
b = drive(['/opt/homebrew/bin/bash', '--norc', '-i'], env)
print(b.decode('utf-8', 'replace'))
print("############ PSH interactive ############")
os.chdir('/Users/pwilson/src/psh-r22-verify')
p = drive([sys.executable, '-m', 'psh', '-i'],
          {**env, 'PYTHONPATH': '/Users/pwilson/src/psh-r22-verify'})
print(p.decode('utf-8', 'replace'))
