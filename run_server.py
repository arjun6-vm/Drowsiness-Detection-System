import os
import subprocess
import sys

port = os.environ.get('PORT', '10000')
print(f'[SafeDrive Boot] Starting Gunicorn on port {port}...')
cmd = [
    sys.executable, '-m', 'gunicorn',
    '--bind', f'0.0.0.0:{port}',
    '--workers', '1',
    '--threads', '4',
    '--timeout', '120',
    'app:app'
]
sys.exit(subprocess.call(cmd))
