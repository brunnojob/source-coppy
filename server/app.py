"""Authenticated business operations. SQLite lives only on the server."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

DB_PATH = Path(os.getenv('BS_DATABASE', str(Path(__file__).parent / 'data' / 'business.sqlite3')))
SESSION_TTL = 8 * 3600

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def ident():
    return str(uuid.uuid4())

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(value, salt=None):
    salt = salt or secrets.token_hex(16)
    result = hashlib.scrypt(value.encode(), salt=salt.encode(), n=32768, r=8, p=1, maxmem=64*1024*1024, dklen=64)
    return f'scrypt${salt}${result.hex()}'

def password_ok(value, encoded):
    try:
        _, salt, _ = encoded.split('$')
        return hmac.compare_digest(password_hash(value, salt), encoded)
    except (ValueError, TypeError):
        return False

DUMMY_HASH = password_hash('A-constant-only-for-timing-not-an-account')

def connect():
    db = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=30000')
    return db

def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript((Path(__file__).parent / 'schema.sql').read_text())
        if db.execute('SELECT MAX(version) FROM schema_version').fetchone()[0] != 1:
            raise RuntimeError('Unsupported database schema version')
    os.chmod(DB_PATH, 0o600)

@contextmanager
def transaction():
    db = connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def audit(db, actor, action, entity):
    db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)', (ident(), actor['business_id'], actor['id'], action, entity, now()))

def require(actor, *roles):
    if actor['role'] not in roles:
        raise HTTPException(403, 'role_forbidden')

def find(db, table, entity_id, actor):
    # Table names are internal constants, never caller input.
    row = db.execute(f'SELECT * FROM {table} WHERE id=? AND business_id=?', (entity_id, actor['business_id'])).fetchone()
    if not row:
        raise HTTPException(404, 'not_found')
    return dict(row)

def public_user(row):
    return {k: row[k] for k in ('id', 'business_id', 'email', 'name', 'role', 'active')}

def issue_session(db, user_id):
    token = secrets.token_urlsafe(48)
    db.execute('DELETE FROM sessions WHERE expires_at < ?', (int(time.time()),))
    db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token), user_id, int(time.time())+SESSION_TTL))
    return token

class BodyLimitMiddleware:
    def __init__(self, app, limit=25_000_000):
        self.app, self.limit = app, limit
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        size = 0
        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get('body', b''))
            if size > self.limit:
                raise HTTPException(413, 'request_too_large')
            return message
        await self.app(scope, limited_receive, send)

app = FastAPI(title="bsystem's Business API", version='2.0.0', docs_url='/docs')
origins = [s.strip() for s in os.getenv('BS_CORS_ORIGINS', 'https://brunnojob.github.io,http://localhost:8000,http://127.0.0.1:8000').split(',') if s.strip()]
if '*' in origins:
    raise RuntimeError('Use explicit CORS origins')
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=['GET','POST','PATCH'], allow_headers=['Authorization','Content-Type'])

@app.middleware('http')
async def response_headers(request: Request, call_next):
    try:
        length = int(request.headers.get('content-length', '0'))
    except ValueError:
        length = 25_000_001
    if length > 25_000_000:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'request_too_large'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

@app.on_event('startup')
def startup():
    initialize()

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

RawPassword = Annotated[str, StringConstraints(strip_whitespace=False)]

class Credentials(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: RawPassword = Field(min_length=1, max_length=128)

class Invite(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=100)
    role: Literal['manager','cashier','member']
    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if '@' not in value or '.' not in value.split('@')[-1]:
            raise ValueError('Invalid email')
        return value.lower()

class AcceptInvite(StrictModel):
    token: str = Field(min_length=20, max_length=200)
    password: RawPassword = Field(min_length=12, max_length=128)

class PasswordChange(StrictModel):
    old_password: RawPassword = Field(min_length=1, max_length=128)
    new_password: RawPassword = Field(min_length=12, max_length=128)

class Product(StrictModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=160)
    price_cents: int = Field(strict=True, ge=0, le=100_000_000)
    stock: int = Field(strict=True, ge=0, le=100_000_000, default=0)
    track_stock: bool = True

class ProductEdit(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    price_cents: int = Field(strict=True, ge=0, le=100_000_000)
    active: bool = True
    version: int = Field(strict=True, ge=1)

class StockAdjustment(StrictModel):
    delta: int = Field(strict=True, ge=-100_000_000, le=100_000_000)
    reason: str = Field(min_length=3, max_length=300)

class Customer(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(max_length=254, default='')
    phone: str = Field(max_length=40, default='')
    notes: str = Field(max_length=2000, default='')
    active: bool = True

class Task(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    status: Literal['todo','doing','done'] = 'todo'
    assignee_id: str | None = None
    due_date: str = ''
    version: int = Field(strict=True, ge=1, default=1)
    @field_validator('due_date')
    @classmethod
    def valid_date(cls, value):
        if value:
            date.fromisoformat(value)
        return value

class ShiftOpen(StrictModel):
    opening_cents: int = Field(strict=True, ge=0, le=100_000_000)

class ShiftClose(StrictModel):
    declared_cents: int = Field(strict=True, ge=0, le=100_000_000)

class SaleItem(StrictModel):
    product_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(strict=True, ge=1, le=10000)

class Sale(StrictModel):
    items: list[SaleItem] = Field(min_length=1, max_length=100)
    customer_id: str | None = None
    discount_cents: int = Field(strict=True, ge=0, le=100_000_000, default=0)
    payment_method: Literal['cash','card','pix','other']
    idempotency_key: str = Field(min_length=16, max_length=100)

class Refund(StrictModel):
    reason: str = Field(min_length=3, max_length=500)

class MemberChange(StrictModel):
    role: Literal['manager','cashier','member']
    active: bool

class ProjectDoc(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    document: dict
    version: int = Field(strict=True, ge=0, default=0)


def current_user(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'login_required')
    token = authorization[7:]
    with closing(connect()) as db:
        row = db.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1', (digest(token), int(time.time()))).fetchone()
    if not row:
        raise HTTPException(401, 'session_expired')
    return dict(row)

Actor = Annotated[dict, Depends(current_user)]

@app.get('/health')
def health():
    with closing(connect()) as db:
        db.execute('SELECT 1').fetchone()
    return {'status':'ok','version':'2.0.0'}

@app.post('/auth/login')
def login(data: Credentials, request: Request):
    stamp = int(time.time())
    email = data.email.lower()
    keys = [(digest((request.client.host if request.client else 'unknown')+'|'+email),10), (digest((request.client.host if request.client else 'unknown')+'|all'),80)]
    with transaction() as db:
        db.execute('DELETE FROM login_attempts WHERE reset_at<?', (stamp,))
        for key, limit in keys:
            attempt = db.execute('SELECT count FROM login_attempts WHERE key=?', (key,)).fetchone()
            if attempt and attempt['count'] >= limit:
                raise HTTPException(429, 'try_again_later')
        row = db.execute('SELECT * FROM users WHERE email=? AND active=1', (email,)).fetchone()
        valid = password_ok(data.password, row['password_hash'] if row else DUMMY_HASH)
        if not valid:
            for key, _ in keys:
                db.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key,stamp+900))
            # Commit failed-attempt counters before returning an error.
            db.commit()
            raise HTTPException(401, 'invalid_credentials')
        db.execute('DELETE FROM login_attempts WHERE key=?', (keys[0][0],))
        token = issue_session(db,row['id'])
        audit(db,row,'login',row['id'])
        return {'token':token,'user':public_user(row),'expires_in':SESSION_TTL}

@app.post('/auth/logout')
def logout(actor: Actor, authorization: Annotated[str,Header()]):
    with transaction() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?',(digest(authorization[7:]),))
    return {'ok':True}

@app.get('/me')
def me(actor: Actor):
    with closing(connect()) as db:
        business = dict(db.execute('SELECT id,name,currency FROM businesses WHERE id=?',(actor['business_id'],)).fetchone())
    return {'user':public_user(actor),'business':business}

@app.post('/auth/password')
def change_password(data: PasswordChange, actor: Actor):
    if not password_ok(data.old_password,actor['password_hash']):
        raise HTTPException(401,'invalid_credentials')
    with transaction() as db:
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(data.new_password),actor['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(actor['id'],))
        audit(db,actor,'password_changed',actor['id'])
    return {'ok':True,'login_required':True}

@app.get('/team')
def team(actor: Actor):
    with closing(connect()) as db:
        return [public_user(row) for row in db.execute('SELECT * FROM users WHERE business_id=? ORDER BY name',(actor['business_id'],))]

@app.post('/team/invites')
def invite(data: Invite, actor: Actor):
    require(actor,'owner')
    token=secrets.token_urlsafe(40)
    with transaction() as db:
        if db.execute('SELECT 1 FROM users WHERE email=?',(data.email,)).fetchone():
            raise HTTPException(409,'email_in_use')
        db.execute('UPDATE invites SET used=1 WHERE business_id=? AND email=?',(actor['business_id'],data.email))
        invitation=ident()
        db.execute('INSERT INTO invites VALUES(?,?,?,?,?,?,?,0)',(invitation,actor['business_id'],data.email,data.name,data.role,digest(token),int(time.time())+86400))
        audit(db,actor,'invite_created',invitation)
    return {'token':token,'expires_in':86400,'email':data.email}

@app.post('/auth/accept-invite')
def accept_invite(data: AcceptInvite):
    with transaction() as db:
        row=db.execute('SELECT * FROM invites WHERE token_hash=? AND used=0 AND expires_at>?',(digest(data.token),int(time.time()))).fetchone()
        if not row:
            raise HTTPException(400,'invalid_invite')
        if db.execute('SELECT 1 FROM users WHERE email=?',(row['email'],)).fetchone():
            raise HTTPException(409,'email_in_use')
        user=ident()
        db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,1,?)',(user,row['business_id'],row['email'],row['name'],password_hash(data.password),row['role'],now()))
        db.execute('UPDATE invites SET used=1 WHERE id=?',(row['id'],))
        actor={'id':user,'business_id':row['business_id']}
        audit(db,actor,'invite_accepted',row['id'])
    return {'ok':True}

@app.patch('/team/{user_id}')
def edit_member(user_id: str, data: MemberChange, actor: Actor):
    require(actor,'owner')
    with transaction() as db:
        target=find(db,'users',user_id,actor)
        if target['role']=='owner' or user_id==actor['id']:
            raise HTTPException(409,'owner_protected')
        db.execute('UPDATE users SET role=?,active=? WHERE id=?',(data.role,int(data.active),user_id))
        db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        audit(db,actor,'member_updated',user_id)
    return {'ok':True}

@app.get('/products')
def products(actor: Actor):
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT * FROM products WHERE business_id=? ORDER BY name',(actor['business_id'],))]

@app.post('/products')
def add_product(data: Product, actor: Actor):
    require(actor,'owner','manager')
    product=ident()
    try:
        with transaction() as db:
            db.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?,1,?)',(product,actor['business_id'],data.sku,data.name,data.price_cents,data.stock,int(data.track_stock),1,now()))
            db.execute('INSERT INTO stock_movements VALUES(?,?,?,?,?,?,?)',(ident(),actor['business_id'],product,data.stock,'initial_stock',actor['id'],now()))
            audit(db,actor,'product_created',product)
    except sqlite3.IntegrityError:
        raise HTTPException(409,'sku_in_use')
    return {'id':product}

@app.patch('/products/{product_id}')
def edit_product(product_id: str, data: ProductEdit, actor: Actor):
    require(actor,'owner','manager')
    with transaction() as db:
        find(db,'products',product_id,actor)
        result=db.execute('UPDATE products SET name=?,price_cents=?,active=?,version=version+1 WHERE id=? AND business_id=? AND version=?',(data.name,data.price_cents,int(data.active),product_id,actor['business_id'],data.version))
        if result.rowcount!=1:
            raise HTTPException(409,'version_conflict')
        audit(db,actor,'product_updated',product_id)
    return {'ok':True}

@app.post('/products/{product_id}/stock')
def adjust_stock(product_id: str,data: StockAdjustment,actor: Actor):
    require(actor,'owner','manager')
    with transaction() as db:
        row=find(db,'products',product_id,actor)
        if row['stock']+data.delta<0:
            raise HTTPException(409,'insufficient_stock')
        db.execute('UPDATE products SET stock=stock+?,version=version+1 WHERE id=?',(data.delta,product_id))
        db.execute('INSERT INTO stock_movements VALUES(?,?,?,?,?,?,?)',(ident(),actor['business_id'],product_id,data.delta,data.reason,actor['id'],now()))
        audit(db,actor,'stock_adjusted',product_id)
    return {'ok':True}

@app.get('/stock-movements')
def movements(actor: Actor):
    require(actor,'owner','manager')
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT m.*,p.name FROM stock_movements m JOIN products p ON p.id=m.product_id WHERE m.business_id=? ORDER BY m.created_at DESC LIMIT 500',(actor['business_id'],))]

@app.get('/customers')
def customers(actor: Actor):
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT * FROM customers WHERE business_id=? ORDER BY name',(actor['business_id'],))]

@app.post('/customers')
def add_customer(data: Customer,actor: Actor):
    require(actor,'owner','manager','member')
    customer=ident()
    with transaction() as db:
        db.execute('INSERT INTO customers VALUES(?,?,?,?,?,?,?,?)',(customer,actor['business_id'],data.name,data.email,data.phone,data.notes,int(data.active),now()))
        audit(db,actor,'customer_created',customer)
    return {'id':customer}

@app.patch('/customers/{customer_id}')
def edit_customer(customer_id: str,data: Customer,actor: Actor):
    require(actor,'owner','manager','member')
    with transaction() as db:
        find(db,'customers',customer_id,actor)
        db.execute('UPDATE customers SET name=?,email=?,phone=?,notes=?,active=? WHERE id=?',(data.name,data.email,data.phone,data.notes,int(data.active),customer_id))
        audit(db,actor,'customer_updated',customer_id)
    return {'ok':True}

@app.get('/tasks')
def tasks(actor: Actor):
    require(actor,'owner','manager','member')
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT * FROM tasks WHERE business_id=? ORDER BY created_at DESC',(actor['business_id'],))]

def validate_assignee(db,data,actor):
    if data.assignee_id:
        row=find(db,'users',data.assignee_id,actor)
        if not row['active']:
            raise HTTPException(400,'inactive_assignee')

@app.post('/tasks')
def add_task(data: Task,actor: Actor):
    require(actor,'owner','manager','member')
    task=ident()
    with transaction() as db:
        validate_assignee(db,data,actor)
        db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,1,?)',(task,actor['business_id'],data.title,data.status,data.assignee_id,data.due_date,now()))
        audit(db,actor,'task_created',task)
    return {'id':task}

@app.patch('/tasks/{task_id}')
def edit_task(task_id: str,data: Task,actor: Actor):
    require(actor,'owner','manager','member')
    with transaction() as db:
        find(db,'tasks',task_id,actor)
        validate_assignee(db,data,actor)
        result=db.execute('UPDATE tasks SET title=?,status=?,assignee_id=?,due_date=?,version=version+1 WHERE id=? AND business_id=? AND version=?',(data.title,data.status,data.assignee_id,data.due_date,task_id,actor['business_id'],data.version))
        if result.rowcount!=1:
            raise HTTPException(409,'version_conflict')
        audit(db,actor,'task_updated',task_id)
    return {'ok':True}

def open_shift(db,actor):
    row=db.execute('SELECT * FROM shifts WHERE business_id=? AND user_id=? AND closed_at IS NULL',(actor['business_id'],actor['id'])).fetchone()
    if not row:
        raise HTTPException(409,'open_shift_required')
    return dict(row)

def expected_cash(db,shift):
    paid=db.execute("SELECT COALESCE(SUM(total_cents),0) FROM sales WHERE shift_id=? AND payment_method='cash'",(shift['id'],)).fetchone()[0]
    refunded=db.execute("SELECT COALESCE(SUM(r.total_cents),0) FROM refunds r JOIN sales s ON s.id=r.sale_id WHERE r.shift_id=? AND s.payment_method='cash'",(shift['id'],)).fetchone()[0]
    return shift['opening_cents']+paid-refunded

@app.get('/shifts')
def shifts(actor: Actor):
    with closing(connect()) as db:
        sql='SELECT * FROM shifts WHERE business_id=?'
        args=[actor['business_id']]
        if actor['role'] not in ('owner','manager'):
            sql+=' AND user_id=?';args.append(actor['id'])
        rows=[dict(r) for r in db.execute(sql+' ORDER BY opened_at DESC LIMIT 100',args)]
        for row in rows:
            if row['closed_at'] is None:
                row['expected_cents']=expected_cash(db,row)
        return rows

@app.post('/shifts/open')
def start_shift(data: ShiftOpen,actor: Actor):
    require(actor,'owner','manager','cashier')
    shift=ident()
    with transaction() as db:
        if db.execute('SELECT 1 FROM shifts WHERE user_id=? AND closed_at IS NULL',(actor['id'],)).fetchone():
            raise HTTPException(409,'shift_already_open')
        db.execute('INSERT INTO shifts VALUES(?,?,?,?,?,NULL,NULL,NULL)',(shift,actor['business_id'],actor['id'],data.opening_cents,now()))
        audit(db,actor,'shift_opened',shift)
    return {'id':shift}

@app.post('/shifts/{shift_id}/close')
def close_shift(shift_id: str,data: ShiftClose,actor: Actor):
    require(actor,'owner','manager','cashier')
    with transaction() as db:
        shift=find(db,'shifts',shift_id,actor)
        if shift['user_id']!=actor['id'] or shift['closed_at']:
            raise HTTPException(409,'shift_not_open_for_user')
        expected=expected_cash(db,shift)
        db.execute('UPDATE shifts SET closed_at=?,declared_cents=?,expected_cents=? WHERE id=?',(now(),data.declared_cents,expected,shift_id))
        audit(db,actor,'shift_closed',shift_id)
    return {'expected_cents':expected,'declared_cents':data.declared_cents,'difference_cents':data.declared_cents-expected}

def sale_details(db,sale_id,actor):
    sale=find(db,'sales',sale_id,actor)
    sale['items']=[dict(r) for r in db.execute('SELECT product_id,name,quantity,price_cents FROM sale_items WHERE sale_id=?',(sale_id,))]
    return sale

@app.post('/sales')
def create_sale(data: Sale,actor: Actor):
    require(actor,'owner','manager','cashier')
    payload=data.model_dump()
    fingerprint=digest(json.dumps(payload,sort_keys=True))
    with transaction() as db:
        previous=db.execute('SELECT * FROM sales WHERE business_id=? AND idempotency_key=?',(actor['business_id'],data.idempotency_key)).fetchone()
        if previous:
            if previous['request_hash']!=fingerprint or previous['user_id']!=actor['id']:
                raise HTTPException(409,'idempotency_conflict')
            return sale_details(db,previous['id'],actor)
        shift=open_shift(db,actor)
        if data.customer_id:
            customer=find(db,'customers',data.customer_id,actor)
            if not customer['active']:
                raise HTTPException(409,'inactive_customer')
        if data.discount_cents:
            require(actor,'owner','manager')
        quantities={}
        for item in data.items:
            quantities[item.product_id]=quantities.get(item.product_id,0)+item.quantity
        subtotal=0; selected=[]
        for product_id,quantity in quantities.items():
            product=find(db,'products',product_id,actor)
            if not product['active']:
                raise HTTPException(409,'inactive_product')
            if product['track_stock'] and product['stock']<quantity:
                raise HTTPException(409,'insufficient_stock')
            subtotal+=product['price_cents']*quantity
            selected.append((product,quantity))
        if data.discount_cents>subtotal or subtotal>1_000_000_000:
            raise HTTPException(400,'invalid_total')
        sale=ident();stamp=now()
        db.execute('INSERT INTO sales VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(sale,actor['business_id'],actor['id'],shift['id'],data.customer_id,subtotal,data.discount_cents,subtotal-data.discount_cents,data.payment_method,'completed',data.idempotency_key,fingerprint,stamp))
        for product,quantity in selected:
            db.execute('INSERT INTO sale_items VALUES(?,?,?,?,?,?,?)',(ident(),sale,product['id'],product['name'],quantity,product['price_cents'],product['track_stock']))
            if product['track_stock']:
                db.execute('UPDATE products SET stock=stock-?,version=version+1 WHERE id=?',(quantity,product['id']))
                db.execute('INSERT INTO stock_movements VALUES(?,?,?,?,?,?,?)',(ident(),actor['business_id'],product['id'],-quantity,'sale:'+sale,actor['id'],stamp))
        audit(db,actor,'sale_recorded',sale)
        return sale_details(db,sale,actor)

@app.get('/sales')
def sales(actor: Actor):
    require(actor,'owner','manager','cashier')
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT * FROM sales WHERE business_id=? ORDER BY created_at DESC LIMIT 500',(actor['business_id'],))]

@app.get('/sales/{sale_id}')
def read_sale(sale_id: str,actor: Actor):
    require(actor,'owner','manager','cashier')
    with closing(connect()) as db:
        return sale_details(db,sale_id,actor)

@app.post('/sales/{sale_id}/refund')
def refund(sale_id: str,data: Refund,actor: Actor):
    require(actor,'owner','manager')
    with transaction() as db:
        sale=find(db,'sales',sale_id,actor)
        if sale['status']=='refunded':
            return {'ok':True,'already_refunded':True}
        shift=open_shift(db,actor)
        for item in db.execute('SELECT * FROM sale_items WHERE sale_id=?',(sale_id,)):
            if item['track_stock']:
                db.execute('UPDATE products SET stock=stock+?,version=version+1 WHERE id=?',(item['quantity'],item['product_id']))
                db.execute('INSERT INTO stock_movements VALUES(?,?,?,?,?,?,?)',(ident(),actor['business_id'],item['product_id'],item['quantity'],'refund:'+sale_id,actor['id'],now()))
        db.execute("UPDATE sales SET status='refunded' WHERE id=?",(sale_id,))
        db.execute('INSERT INTO refunds VALUES(?,?,?,?,?,?,?,?)',(ident(),actor['business_id'],sale_id,shift['id'],actor['id'],data.reason,sale['total_cents'],now()))
        audit(db,actor,'sale_refunded',sale_id)
    return {'ok':True}

@app.get('/reports')
def reports(actor: Actor):
    require(actor,'owner','manager')
    with closing(connect()) as db:
        daily=[dict(r) for r in db.execute("SELECT substr(created_at,1,10) AS day,COUNT(*) AS sales,SUM(total_cents) AS gross_cents FROM sales WHERE business_id=? GROUP BY day ORDER BY day DESC LIMIT 90",(actor['business_id'],))]
        refunds=[dict(r) for r in db.execute("SELECT substr(created_at,1,10) AS day,SUM(total_cents) AS refunds_cents FROM refunds WHERE business_id=? GROUP BY day ORDER BY day DESC LIMIT 90",(actor['business_id'],))]
        low=[dict(r) for r in db.execute('SELECT id,name,sku,stock FROM products WHERE business_id=? AND active=1 AND track_stock=1 AND stock<=5 ORDER BY stock',(actor['business_id'],))]
        total=db.execute('SELECT COALESCE(SUM(total_cents),0) FROM sales WHERE business_id=?',(actor['business_id'],)).fetchone()[0]
        returned=db.execute('SELECT COALESCE(SUM(total_cents),0) FROM refunds WHERE business_id=?',(actor['business_id'],)).fetchone()[0]
    return {'gross_cents':total,'refunds_cents':returned,'net_cents':total-returned,'daily':daily,'refunds':refunds,'low_stock':low,'timezone':'UTC'}

@app.get('/audit')
def read_audit(actor: Actor):
    require(actor,'owner','manager')
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT a.*,u.name FROM audit a JOIN users u ON u.id=a.user_id WHERE a.business_id=? ORDER BY a.created_at DESC LIMIT 500',(actor['business_id'],))]

@app.get('/projects')
def projects(actor: Actor):
    require(actor,'owner','manager','member')
    with closing(connect()) as db:
        return [dict(r) for r in db.execute('SELECT id,name,version,updated_at FROM projects WHERE business_id=? ORDER BY updated_at DESC',(actor['business_id'],))]

@app.get('/projects/{project_id}')
def project(project_id: str,actor: Actor):
    require(actor,'owner','manager','member')
    with closing(connect()) as db:
        row=find(db,'projects',project_id,actor)
    row['document']=json.loads(row['document'])
    return row

@app.post('/projects/{project_id}')
def save_project(project_id: str,data: ProjectDoc,actor: Actor):
    require(actor,'owner','manager','member')
    if len(project_id)>80 or not project_id.replace('-','').isalnum():
        raise HTTPException(400,'invalid_project_id')
    document=json.dumps(data.document,ensure_ascii=False)
    if len(document.encode())>20_000_000 or data.document.get('version')!=2 or not isinstance(data.document.get('pages'),list) or not 1<=len(data.document['pages'])<=30:
        raise HTTPException(400,'invalid_project_document')
    with transaction() as db:
        existing=db.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone()
        if existing:
            if existing['business_id']!=actor['business_id']:
                raise HTTPException(404,'not_found')
            if existing['version']!=data.version:
                raise HTTPException(409,'version_conflict')
            db.execute('UPDATE projects SET name=?,document=?,version=version+1,updated_at=? WHERE id=?',(data.name,document,now(),project_id))
            version=data.version+1
        else:
            if data.version!=0:
                raise HTTPException(409,'version_conflict')
            db.execute('INSERT INTO projects VALUES(?,?,?,?,1,?)',(project_id,actor['business_id'],data.name,document,now()))
            version=1
        audit(db,actor,'project_saved',project_id)
    return {'id':project_id,'version':version}
