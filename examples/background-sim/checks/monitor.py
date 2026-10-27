"""Send Renode monitor commands to the background emulation and print the replies.

    python3 checks/monitor.py 'mach set "mcu"' 'sysbus GetSymbolAddress "main"'

The port comes from $HECTOR_MONITOR_PORT, which hector sets for `requires_sim: true`
tests. Exits non-zero if a command reports an error.
"""

import os
import re
import socket
import sys

PROMPT = re.compile(r"\([^()\r\n]*\) $")
TELNET = re.compile(rb"\xff[\xfb-\xfe].|\xff[\xf0-\xfa]")


def read_prompt(sock):
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            sys.exit("monitor closed the connection")
        buf += chunk
        text = TELNET.sub(b"", buf).decode(errors="replace").replace("\r", "")
        if PROMPT.search(text):
            return text


sock = socket.create_connection(("127.0.0.1", int(os.environ["HECTOR_MONITOR_PORT"])),
                                timeout=30)
# Only the first client gets a banner; a newline makes the monitor print its prompt.
sock.sendall(b"\n")
read_prompt(sock)
for command in sys.argv[1:]:
    sock.sendall(f"{command}\n".encode())
    reply = read_prompt(sock)
    print(reply)
    if "There was an error" in reply:
        sys.exit(1)
