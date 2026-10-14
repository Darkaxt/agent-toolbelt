"""Build the standalone broker with the installed Windows framework compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

FAMILY = Path(__file__).resolve().parents[1]


def build(output):
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise RuntimeError('Installed 64-bit .NET Framework C# compiler is required')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
               '/warnaserror+', '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
               '/r:System.Web.Extensions.dll', '/r:Microsoft.CSharp.dll', '/out:' + str(output),
               str(FAMILY / 'assets/WindowsElevationBroker.cs')]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Broker compile failed:\n' + result.stdout + result.stderr)
    check = subprocess.run([str(output), '--self-test'], capture_output=True, text=True,
                           env=dict(os.environ, TEMP=str(output.parent), TMP=str(output.parent)))
    if check.returncode or not json.loads(check.stdout).get('ok'):
        raise RuntimeError('Broker self-test failed: ' + check.stdout + check.stderr)
    return {'ok': True, 'broker': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'self_test': json.loads(check.stdout)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
