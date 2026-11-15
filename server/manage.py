"""Local operator commands. Never expose these as HTTP endpoints."""
import argparse
import getpass
import sqlite3
from . import app as api

def main():
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest='command',required=True)
    bootstrap=commands.add_parser('bootstrap',help='Create a business and owner')
    bootstrap.add_argument('--business',required=True)
    bootstrap.add_argument('--email',required=True)
    bootstrap.add_argument('--name',required=True)
    backup=commands.add_parser('backup',help='Create a consistent SQLite backup')
    backup.add_argument('path')
    reset=commands.add_parser('reset-password',help='Local recovery; revokes all user sessions')
    reset.add_argument('--email',required=True)
    args=parser.parse_args();api.initialize()
    if args.command=='backup':
        from pathlib import Path
        path=Path(args.path)
        if path.resolve()==api.DB_PATH.resolve() or path.exists():
            parser.error('Choose a new backup file outside the active database')
        with api.connect() as src,sqlite3.connect(path) as dst:src.backup(dst)
        path.chmod(0o600);print('Backup created. Protect it as private business data.');return
    password=getpass.getpass('New password (12+ characters): ')
    if len(password)<12 or len(password)>128 or password!=getpass.getpass('Repeat password: '):
        parser.error('Passwords must match and contain 12–128 characters')
    email=args.email.lower().strip()
    if '@' not in email or '.' not in email.split('@')[-1]:parser.error('Invalid email')
    with api.transaction() as db:
        if args.command=='bootstrap':
            if db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():parser.error('Email already in use')
            business=api.ident();user=api.ident()
            db.execute('INSERT INTO businesses VALUES(?,?,?,?)',(business,args.business,'BRL',api.now()))
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1,?)',(user,business,email,args.name,api.password_hash(password),'owner',api.now()))
            api.audit(db,{'business_id':business,'id':user},'business_created',business)
        else:
            user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not user:parser.error('User not found')
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(api.password_hash(password),user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
            api.audit(db,user,'password_reset_locally',user['id'])
    print('Done. Sign in through operations.html.')
if __name__=='__main__':main()
