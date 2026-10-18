"""Terminal-only recovery. Never pass passwords as command-line arguments."""
import getpass, os, sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash
path=Path(os.environ.get('DATA_DIR','./data'))/'rounded.sqlite'
if not path.exists(): raise SystemExit('Database not found. Check DATA_DIR.')
email=input('Account email: ').strip().lower()
conn=sqlite3.connect(path)
user=conn.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
if not user: raise SystemExit('No matching account.')
p=getpass.getpass('New password (12–256 characters): ')
if not 12<=len(p)<=256: raise SystemExit('Invalid password length.')
if p!=getpass.getpass('Confirm password: '): raise SystemExit('Passwords do not match.')
columns={row[1] for row in conn.execute('PRAGMA table_info(users)')}
extra=",must_change_password=0,invite_expires=0,invite_status='accepted'" if 'must_change_password' in columns else ''
reset_2fa='totp_enabled' in columns and input('Also reset two-factor authentication? [y/N]: ').strip().lower()=='y'
if reset_2fa: extra+=",totp_enabled=0,totp_secret='',totp_pending='',totp_pending_until=0,totp_last_step=-1,recovery_hashes='[]'"
conn.execute('UPDATE users SET password=?,version=version+1'+extra+' WHERE id=?',(generate_password_hash(p),user[0]))
if reset_2fa: conn.execute("INSERT INTO audit(user_id,action,entity) VALUES (NULL,'terminal 2FA reset',?)",(str(user[0]),))
conn.execute("INSERT INTO audit(user_id,action,entity) VALUES (NULL,'terminal password reset',?)",(str(user[0]),))
conn.commit();conn.close();print('Password reset. Existing sessions revoked. Disabled accounts remain disabled.')
