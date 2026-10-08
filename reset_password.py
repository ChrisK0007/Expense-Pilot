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
conn.execute('UPDATE users SET password=?,version=version+1 WHERE id=?',(generate_password_hash(p),user[0]))
conn.execute("INSERT INTO audit(user_id,action,entity) VALUES (NULL,'terminal password reset',?)",(str(user[0]),))
conn.commit();conn.close();print('Password reset. Existing sessions revoked. Disabled accounts remain disabled.')
