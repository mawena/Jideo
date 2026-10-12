import subprocess
import sys

SCRIPT = """
import socket

def refuse(*args, **kwargs):
    raise OSError("réseau interdit")

socket.socket.connect = refuse
socket.create_connection = refuse
import insightface.app
"""


def test_importing_insightface_makes_no_network_call():
    proc = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "pypi" not in proc.stderr.lower()
    assert "Error fetching version" not in proc.stderr
