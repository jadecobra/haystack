#!/usr/bin/env python3
"""Double-fork daemonize so agent shells cannot reap the server."""
import os
import sys
import time

if len(sys.argv) < 4:
    sys.stderr.write("usage: daemonize.py PIDFILE LOGFILE CWD CMD...\n")
    sys.exit(2)

pidfile, logfile, cwd = sys.argv[1], sys.argv[2], sys.argv[3]
cmd = sys.argv[4:]
if not cmd:
    sys.stderr.write("usage: daemonize.py PIDFILE LOGFILE CWD CMD...\n")
    sys.exit(2)

if os.fork() > 0:
    for _ in range(80):
        try:
            if os.path.exists(pidfile) and os.path.getsize(pidfile) > 0:
                os._exit(0)
        except OSError:
            pass
        time.sleep(0.05)
    sys.stderr.write("daemonize: pidfile not written: %s\n" % pidfile)
    os._exit(1)

os.setsid()
if os.fork() > 0:
    os._exit(0)

os.umask(0o22)
os.chdir(cwd)
with open(pidfile, "w", encoding="utf-8") as fh:
    fh.write(str(os.getpid()))
    fh.write("\n")

devnull = os.open(os.devnull, os.O_RDONLY)
logfd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(devnull, 0)
os.dup2(logfd, 1)
os.dup2(logfd, 2)
if devnull > 2:
    os.close(devnull)
if logfd > 2:
    os.close(logfd)

os.execvpe(cmd[0], cmd, os.environ)
