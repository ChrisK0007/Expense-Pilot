"""Offline recovery of encrypted archives made by beta.11; no running backup service."""
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'EXPENSE-PILOT-BACKUP-1\n'


def decrypt(source,target,key):
    with open(source,'rb') as inp:
        length=os.fstat(inp.fileno()).st_size
        if length<len(MAGIC)+12+16 or length>100*1024**3: raise ValueError('Invalid encrypted backup size.')
        header=inp.read(len(MAGIC)+12)
        if not header.startswith(MAGIC): raise ValueError('Unsupported encrypted backup format.')
        inp.seek(-16,2);tag=inp.read(16);inp.seek(len(header))
        decryptor=Cipher(algorithms.AES(key),modes.GCM(header[-12:],tag)).decryptor();decryptor.authenticate_additional_data(header)
        remaining=length-len(header)-16
        created=False
        try:
            with open(target,'xb') as out:
                created=True
                os.chmod(target,0o600)
                while remaining:
                    chunk=inp.read(min(1024*1024,remaining))
                    if not chunk: raise ValueError('Encrypted backup is incomplete.')
                    remaining-=len(chunk);out.write(decryptor.update(chunk))
                out.write(decryptor.finalize())
        except Exception:
            if created: Path(target).unlink(missing_ok=True)
            raise



if __name__=='__main__':
    import argparse
    import getpass
    parser=argparse.ArgumentParser(description='Decrypt an Expense Pilot backup. Then use restore_backup.py with an empty data directory.')
    parser.add_argument('archive');parser.add_argument('output');args=parser.parse_args()
    try:
        key=base64.urlsafe_b64decode(getpass.getpass('Recovery key: ').strip());decrypt(args.archive,args.output,key)
    except Exception: parser.exit(1,'Decryption failed. Check the recovery key and encrypted archive.\n')
    print('Decrypted ZIP written. Keep it private and use restore_backup.py to restore it.')
