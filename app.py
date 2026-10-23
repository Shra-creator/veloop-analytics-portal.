import os, math, re
from urllib.parse import urlparse
import pandas as pd
from flask import Flask, request, redirect, url_for, flash, send_file, render_template_string, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, current_user, login_user, login_required, logout_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'local-only-change-this-secret-key-before-deploying'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true' and bool(os.environ.get('RENDER'))
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 8

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data')
DEFAULT = os.path.join(DATA, 'users.csv')
os.makedirs(DATA, exist_ok=True)

database_url = os.environ.get('DATABASE_URL', '').strip()
if database_url.startswith('postgres://'):
    database_url = 'postgresql://' + database_url[len('postgres://'):]
if not database_url:
    database_url = 'sqlite:///' + os.path.join(DATA, 'velop_auth.db')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True} if database_url.startswith('postgresql') else {}

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access the analytics dashboard.'
login_manager.login_message_category = 'warning'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None

with app.app_context():
    db.create_all()

NAV = [('dashboard','Overview','/'),('users','User explorer','/users'),('quality','Data quality','/quality'),('kpis','KPI catalogue','/kpis'),('insights','Insights & gaps','/insights'),('backlog','Action backlog','/backlog')]

def data_path():
    if current_user.is_authenticated:
        user_active = os.path.join(DATA, f'user_{current_user.get_id()}_active.csv')
        if os.path.exists(user_active):
            return user_active
    return DEFAULT

def get_df():
    try: return pd.read_csv(data_path(), low_memory=False)
    except Exception: return pd.DataFrame()
def find_col(df, *needles):
    for c in df.columns:
        if any(n in str(c).lower() for n in needles): return c
    return None
def truth(v): return str(v).strip().lower() in ('true','yes','1','y','verified','completed','complete') if pd.notna(v) else False
def summary(df):
    uid=find_col(df,'user_id','userid','user id'); email=find_col(df,'email_verification_status','email_verified'); onboard=find_col(df,'onboarding_status');
    active7=find_col(df,'is_active_7d','active_last_7_days'); active30=find_col(df,'is_active_30d','active_last_30_days')
    return {'rows':len(df),'cols':len(df.columns),'unique':int(df[uid].nunique()) if uid else len(df),'missing':int(df.isna().sum().sum()),'duplicates':int(df.duplicated().sum()),'dupids':int(df[uid].duplicated().sum()) if uid else None,
      'email_rate':round(df[email].astype(str).str.lower().isin(['verified','true','yes','1']).mean()*100,1) if email and len(df) else None,
      'onboard_rate':round(df[onboard].astype(str).str.lower().isin(['completed','complete','done']).mean()*100,1) if onboard and len(df) else None,
      'active7':int(df[active7].map(truth).sum()) if active7 else None,'active30':int(df[active30].map(truth).sum()) if active30 else None}
def counts(df, col):
    if not col or col not in df: return []
    return [{'label':str(k),'value':int(v)} for k,v in df[col].fillna('(Missing)').astype(str).value_counts().head(12).items()]

template = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }} · VELOOP Analytics</title><link rel="stylesheet" href="{{ url_for('static',filename='style.css') }}"><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head><body><div class="shell"><aside class="side"><a class="brand" href="/"><span class="logo">V</span><span><b>VELOOP</b><small>Analytics Portal</small></span></a><p class="navcap">WORKSPACE</p>{% for key,label,href in nav %}<a class="nav {{ 'on' if page==key else '' }}" href="{{ href }}"><span>{{ {'dashboard':'◫','users':'♙','quality':'◈','kpis':'▤','insights':'⌁','backlog':'☷'}[key] }}</span>{{ label }}</a>{% endfor %}<div class="sidebottom"><b>● SIMULATED DATA</b><p>Portfolio demo only. Not live company data.</p></div></aside><main class="main"><header class="top"><span class="crumb">Workspace <i>/</i> {{ title }}</span><span class="local"><b></b> {{ current_user.username }} <form method="post" action="{{ url_for('logout') }}" class="logout-inline"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><button type="submit" class="logout-btn">Log out</button></form></span></header><div class="content">{% with msgs=get_flashed_messages(with_categories=true) %}{% for cat,msg in msgs %}<div class="flash {{cat}}">{{msg}}</div>{% endfor %}{% endwith %}{% if page=='dashboard' %}
<section class="heading"><div><small class="eyebrow">ANALYTICS WORKSPACE</small><h1>Good day, Analyst <span>✦</span></h1><p>Consolidated view of the supplied user dataset.</p></div><div class="actions"><a class="btn secondary" href="/download">↓ Export CSV</a><button class="btn primary" onclick="document.getElementById('upload').classList.toggle('hidden')">＋ Load dataset</button></div></section><div id="upload" class="upload hidden"><form method="post" action="/upload" enctype="multipart/form-data"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><b>Load a CSV or Excel dataset</b><input type="file" name="dataset" accept=".csv,.xlsx,.xls" required><button class="btn primary">Upload & analyse</button></form></div><div class="notice"><b>i</b><div><strong>Simulated data notice</strong><p>The supplied workbook is fictional and for analytical testing. Do not present these figures as actual VELOOP performance.</p></div><small>{{ dataset }}</small></div><section class="cards"><article><label>Total records</label><strong>{{ '{:,}'.format(s.rows) }}</strong><small>Rows in selected dataset</small></article><article><label>Unique users</label><strong>{{ '{:,}'.format(s.unique) }}</strong><small>Distinct detected user IDs</small></article><article><label>Email verified</label><strong>{{ s.email_rate|string+'%' if s.email_rate is not none else 'N/A' }}</strong><small>Calculated from available field</small></article><article><label>Onboarding complete</label><strong>{{ s.onboard_rate|string+'%' if s.onboard_rate is not none else 'N/A' }}</strong><small>Completed status ÷ all rows</small></article></section><section class="minicards"><article><label>Missing cells</label><strong>{{ '{:,}'.format(s.missing) }}</strong><a href="/quality">Inspect →</a></article><article><label>Exact duplicate rows</label><strong>{{ s.duplicates }}</strong><a href="/quality">Inspect →</a></article><article><label>Dataset attributes</label><strong>{{ s.cols }}</strong><a href="/users">Explore →</a></article></section><section class="charts"><article class="panel"><div class="panelhead"><div><h2>Account status</h2><p>Distribution by recorded account status</p></div><small>PROFILE</small></div><div class="chart"><canvas id="status"></canvas></div></article><article class="panel"><div class="panelhead"><div><h2>Acquisition channels</h2><p>Recorded acquisition source</p></div><small>ACQUISITION</small></div><div class="chart"><canvas id="acquisition"></canvas></div></article><article class="panel"><div class="panelhead"><div><h2>Device distribution</h2><p>Recorded primary device</p></div><small>DEVICE</small></div><div class="chart"><canvas id="device"></canvas></div></article><article class="panel"><div class="panelhead"><div><h2>Onboarding status</h2><p>Recorded onboarding state</p></div><small>ONBOARDING</small></div><div class="chart"><canvas id="onboard"></canvas></div></article></section><section class="panel"><div class="panelhead"><div><h2>Continue your analysis</h2><p>Supporting sections in this consolidated portal.</p></div></div><div class="shortcuts"><a href="/users"><b>User explorer</b><small>Search and review records</small><em>Open →</em></a><a href="/quality"><b>Data quality</b><small>Missing values and duplicates</small><em>Open →</em></a><a href="/kpis"><b>KPI catalogue</b><small>Available metrics and data gaps</small><em>Open →</em></a><a href="/backlog"><b>Action backlog</b><small>Prioritized next steps</small><em>Open →</em></a></div></section>
{% elif page=='users' %}<section class="heading"><div><small class="eyebrow">DATA EXPLORATION</small><h1>User explorer</h1><p>Search across columns and inspect user-level records.</p></div><a class="btn secondary" href="/download">↓ Export CSV</a></section><div class="notice"><b>i</b><div><strong>Privacy reminder</strong><p>Included records are simulated. Only upload data you are authorized to use.</p></div></div><section class="panel tablepanel"><form class="filters" method="get"><input type="search" name="q" value="{{ q }}" placeholder="Search any column…"><button class="btn primary">Search</button><a class="btn secondary" href="/users">Clear</a><small>{{ '{:,}'.format(total) }} records found</small></form><div class="tablewrap"><table><thead><tr>{% for c in columns %}<th>{{c}}</th>{% endfor %}</tr></thead><tbody>{% for r in rows %}<tr>{% for c in columns %}<td title="{{r[c]}}">{{r[c]}}</td>{% endfor %}</tr>{% endfor %}{% if not rows %}<tr><td colspan="{{columns|length}}">No matching records.</td></tr>{% endif %}</tbody></table></div><div class="pager"><span>Page {{p}} of {{pages}}</span><div>{% if p>1 %}<a href="/users?q={{q|urlencode}}&page={{p-1}}">← Previous</a>{% endif %} {% if p<pages %}<a href="/users?q={{q|urlencode}}&page={{p+1}}">Next →</a>{% endif %}</div></div></section>
{% elif page=='quality' %}<section class="heading"><div><small class="eyebrow">DATA GOVERNANCE</small><h1>Data quality audit</h1><p>Review missing values and duplicates before trusting a metric.</p></div><a class="btn secondary" href="/download">↓ Download CSV</a></section><section class="cards"><article><label>Records scanned</label><strong>{{s.rows}}</strong></article><article><label>Attributes scanned</label><strong>{{s.cols}}</strong></article><article><label>Missing cells</label><strong>{{s.missing}}</strong></article><article><label>Exact duplicate rows</label><strong>{{s.duplicates}}</strong></article></section><section class="panel tablepanel"><div class="panelhead"><div><h2>Missing values by column</h2><p>Only columns with at least one missing value are listed.</p></div></div><div class="tablewrap"><table class="normal"><thead><tr><th>Column</th><th>Missing cells</th><th>Missing %</th><th>Severity guide</th></tr></thead><tbody>{% for r in missing %}<tr><td><b>{{r.column}}</b></td><td>{{r.count}}</td><td>{{r.pct}}%</td><td><span class="pill {{ 'danger' if r.pct>=20 else 'warning' if r.pct>=5 else 'ok' }}">{{'High' if r.pct>=20 else 'Review' if r.pct>=5 else 'Low'}}</span></td></tr>{% endfor %}</tbody></table></div></section><section class="panel"><h2>Recommended controls</h2><ul><li>Validate date formats and timezone rules.</li><li>Separate expected optional fields from true data defects.</li><li>Check uniqueness of user IDs and transaction IDs.</li><li>Record cleaning decisions in an audit log.</li><li>Do not invent missing transaction or event data.</li></ul></section>
{% elif page=='kpis' %}<section class="heading"><div><small class="eyebrow">METRIC DEFINITIONS</small><h1>KPI catalogue</h1><p>What can be calculated now, and what needs more data.</p></div></section><div class="notice"><b>i</b><div><strong>Metric readiness matters</strong><p>Profile data supports profile-level metrics. Transaction and event KPIs need verified source tables and agreed definitions.</p></div></div><section class="panel tablepanel"><div class="tablewrap"><table class="normal"><thead><tr><th>KPI</th><th>Current value</th><th>Readiness</th><th>Definition / requirement</th></tr></thead><tbody>{% for r in kpis %}<tr><td><b>{{r[0]}}</b></td><td>{{r[1]}}</td><td><span class="pill {{'ok' if r[2]=='Available' else 'warning' if r[2]=='Conditional' else 'neutral'}}">{{r[2]}}</span></td><td>{{r[3]}}</td></tr>{% endfor %}</tbody></table></div></section>
{% elif page=='insights' %}<section class="heading"><div><small class="eyebrow">INTERPRETATION</small><h1>Insights & data gaps</h1><p>Keep observed patterns separate from assumptions and missing evidence.</p></div></section><section class="insights">{% for name,items in groups %}<article class="panel"><div class="panelhead"><div><h2>{{name}}</h2><p>Counts in the selected simulated dataset</p></div></div>{% for x in items %}<div class="rank"><span>{{x.label}}</span><i><b style="width:{{(x.value/(items[0].value or 1)*100)|round}}%"></b></i><strong>{{x.value}}</strong></div>{% endfor %}</article>{% endfor %}</section><section class="panel"><h2>Important limitations</h2><ul><li>These are simulated user-profile records, not verified live company data.</li><li>Reward earnings require a reward-credit or earning transaction table.</li><li>Withdrawal metrics require request/status timestamps and payout outcomes.</li><li>Referral conversion requires invite, signup, and attribution events.</li><li>Retention requires reliable event history and cohort definitions.</li></ul></section>
{% elif page=='backlog' %}<section class="heading"><div><small class="eyebrow">IMPLEMENTATION PLAN</small><h1>Action backlog</h1><p>Suggested steps to move from simulated analysis to dependable analytics.</p></div><span class="pill neutral">PROPOSED</span></section><div class="notice"><b>i</b><div><strong>Proposed actions, not verified implementation</strong><p>This is a suggested analytics backlog. It does not claim these tracking systems already exist.</p></div></div><section class="panel tablepanel"><div class="tablewrap"><table class="normal"><thead><tr><th>Priority</th><th>Work item</th><th>Details</th><th>Suggested owner</th></tr></thead><tbody>{% for r in items %}<tr><td><span class="pill {{'danger' if r[0]=='P1' else 'warning' if r[0]=='P2' else 'neutral'}}">{{r[0]}}</span></td><td><b>{{r[1]}}</b></td><td>{{r[2]}}</td><td>{{r[3]}}</td></tr>{% endfor %}</tbody></table></div></section><section class="panel"><h2>Suggested delivery sequence</h2><div class="sequence"><div><b>01 Validate</b><small>Fields, dates, IDs</small></div><span>→</span><div><b>02 Instrument</b><small>Events and transactions</small></div><span>→</span><div><b>03 Define</b><small>KPI rules and owners</small></div><span>→</span><div><b>04 Automate</b><small>Refresh and monitoring</small></div></div></section>{% endif %}<footer>VELOOP Consolidated Analytics Portal <span>•</span> Built for analytical testing with simulated data</footer></div></main></div>
{% if page=='dashboard' %}<script>const C={{charts|tojson}};function donut(id,a){if(!a.length)return;new Chart(document.getElementById(id),{type:'doughnut',data:{labels:a.map(x=>x.label),datasets:[{data:a.map(x=>x.value),backgroundColor:['#6b5ce7','#8e83f2','#a9a1fa','#4f8de8','#55c5b1','#f2b45c','#ed8aa3','#6c7d9d','#b9c5d7'],borderWidth:0}]},options:{responsive:true,maintainAspectRatio:false,cutout:'68%',plugins:{legend:{position:'bottom',labels:{boxWidth:9,padding:12,font:{size:10}}}}}})}function bars(id,a){if(!a.length)return;new Chart(document.getElementById(id),{type:'bar',data:{labels:a.map(x=>x.label),datasets:[{data:a.map(x=>x.value),backgroundColor:'#7b6be9',borderRadius:5}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{color:'#eff1f6'}},y:{grid:{display:false}}}}})}donut('status',C.status);bars('acquisition',C.acquisition);donut('device',C.device);bars('onboard',C.onboarding);</script>{% endif %}</body></html>'''

AUTH_TEMPLATE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ title }} · VELOOP Analytics</title><link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}"><style>
.auth-wrap{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at top left,#eceaff,transparent 40%),#f7f8fc}.auth-card{width:min(100%,440px);background:#fff;border:1px solid #e7e9f2;border-radius:22px;padding:32px;box-shadow:0 18px 55px #25254a12}.auth-brand{display:flex;align-items:center;gap:12px;margin-bottom:24px}.auth-logo{display:grid;place-items:center;width:44px;height:44px;border-radius:14px;background:#6b5ce7;color:#fff;font-weight:800;font-size:22px}.auth-card h1{margin:0 0 8px;font-size:27px}.auth-sub{color:#73788b;margin:0 0 24px}.auth-card label{display:block;font-size:13px;font-weight:700;margin:14px 0 7px}.auth-card input{width:100%;box-sizing:border-box;padding:12px 13px;border:1px solid #dfe2ec;border-radius:10px;font:inherit}.auth-card input:focus{outline:2px solid #bcb5ff;border-color:#8b7cf0}.auth-card .btn{width:100%;margin-top:20px;justify-content:center}.auth-switch{text-align:center;margin:20px 0 0;color:#73788b;font-size:14px}.auth-switch a{color:#6554d8;font-weight:700}.auth-note{font-size:12px;color:#7c8191;margin-top:20px;line-height:1.5}.auth-card .flash{margin-bottom:12px}
</style></head><body><div class="auth-wrap"><main class="auth-card"><div class="auth-brand"><span class="auth-logo">V</span><div><b>VELOOP</b><div style="font-size:12px;color:#7c8191">Analytics Portal</div></div></div><h1>{{ heading }}</h1><p class="auth-sub">{{ subtitle }}</p>{% with msgs=get_flashed_messages(with_categories=true) %}{% for cat,msg in msgs %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}{% endwith %}<form method="post" novalidate><input type="hidden" name="csrf_token" value="{{ csrf_token() }}">{% if mode == 'register' %}<label for="username">Username</label><input id="username" name="username" type="text" minlength="3" maxlength="30" autocomplete="username" required value="{{ username|default('') }}"><label for="email">Email address</label><input id="email" name="email" type="email" maxlength="254" autocomplete="email" required value="{{ email|default('') }}">{% else %}<label for="identity">Username or email</label><input id="identity" name="identity" type="text" autocomplete="username" required value="{{ identity|default('') }}">{% endif %}<label for="password">Password</label><input id="password" name="password" type="password" minlength="10" autocomplete="{{ 'new-password' if mode == 'register' else 'current-password' }}" required>{% if mode == 'register' %}<p class="auth-note">Use at least 10 characters. A passphrase is a good choice; don't reuse your email password.</p>{% endif %}<button class="btn primary" type="submit">{{ 'Create account' if mode == 'register' else 'Log in' }}</button></form><p class="auth-switch">{% if mode == 'register' %}Already have an account? <a href="{{ url_for('login') }}">Log in</a>{% else %}New to the portal? <a href="{{ url_for('register') }}">Create an account</a>{% endif %}</p><p class="auth-note">Portfolio demonstration using simulated data. Do not upload confidential information.</p></main></div></body></html>'''

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,30}', username):
            flash('Username must be 3–30 characters and use letters, numbers, dots, underscores, or hyphens.', 'error')
        elif not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254:
            flash('Enter a valid email address.', 'error')
        elif len(password) < 10 or len(password) > 128:
            flash('Password must be between 10 and 128 characters.', 'error')
        elif User.query.filter(db.or_(db.func.lower(User.username) == username.lower(), User.email == email)).first():
            flash('That username or email is already registered. Try logging in.', 'error')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash('Account creation failed. Please try again.', 'error')
            else:
                login_user(user, remember=False, fresh=True)
                flash('Your account was created successfully.', 'success')
                return redirect(url_for('dashboard'))
        return render_template_string(AUTH_TEMPLATE, title='Register', heading='Create your account', subtitle='Register to access your analytics workspace.', mode='register', username=username, email=email)
    return render_template_string(AUTH_TEMPLATE, title='Register', heading='Create your account', subtitle='Register to access your analytics workspace.', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        identity = request.form.get('identity', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter(db.or_(db.func.lower(User.username) == identity.lower(), User.email == identity.lower())).first() if identity else None
        if not user or not user.check_password(password):
            flash('Invalid username/email or password.', 'error')
            return render_template_string(AUTH_TEMPLATE, title='Log in', heading='Welcome back', subtitle='Log in to continue to your dashboard.', mode='login', identity=identity), 401
        login_user(user, remember=False, fresh=True)
        target = request.args.get('next', '')
        parsed = urlparse(target)
        if target and not parsed.scheme and not parsed.netloc and target.startswith('/') and not target.startswith('//'):
            return redirect(target)
        return redirect(url_for('dashboard'))
    return render_template_string(AUTH_TEMPLATE, title='Log in', heading='Welcome back', subtitle='Log in to continue to your dashboard.', mode='login')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    df=get_df(); s=summary(df)
    charts={'status':counts(df,find_col(df,'account_status')),'acquisition':counts(df,find_col(df,'acquisition_source','acquisition_channel')),'device':counts(df,find_col(df,'primary_device','device_type')),'onboarding':counts(df,find_col(df,'onboarding_status'))}
    return render_template_string(template,nav=NAV,page='dashboard',title='Overview',s=s,charts=charts,dataset=os.path.basename(data_path()))
@app.route('/users')
@login_required
def users():
    df=get_df(); q=request.args.get('q','').strip()
    if q: df=df[df.astype(str).apply(lambda c:c.str.contains(q,case=False,na=False,regex=False)).any(axis=1)]
    total=len(df); p=max(1,int(request.args.get('page',1))); size=25; pages=max(1,math.ceil(total/size)); p=min(p,pages)
    rows=df.iloc[(p-1)*size:p*size].fillna('').to_dict('records')
    return render_template_string(template,nav=NAV,page='users',title='User explorer',columns=list(df.columns),rows=rows,q=q,total=total,p=p,pages=pages)
@app.route('/quality')
@login_required
def quality():
    df=get_df(); missing=[]
    for c,n in df.isna().sum().items():
        if n: missing.append({'column':str(c),'count':int(n),'pct':round(n/len(df)*100,1) if len(df) else 0})
    missing.sort(key=lambda x:x['count'],reverse=True)
    return render_template_string(template,nav=NAV,page='quality',title='Data quality',s=summary(df),missing=missing)
@app.route('/kpis')
@login_required
def kpis():
    df=get_df(); s=summary(df)
    items=[('Total user records',str(s['rows']),'Available','Count of rows in the selected dataset.'),('Unique users',str(s['unique']),'Available','Distinct user IDs; falls back to row count if no ID column is detected.'),('Email verification rate',str(s['email_rate'])+'%' if s['email_rate'] is not None else 'Not available','Conditional','Calculated only if an email verification status field is present.'),('Onboarding completion rate',str(s['onboard_rate'])+'%' if s['onboard_rate'] is not None else 'Not available','Conditional','Completed status divided by all rows; confirm the denominator before business reporting.'),('Missing cells',str(s['missing']),'Available','Total null cells detected.'),('Exact duplicate rows',str(s['duplicates']),'Available','Rows identical across all columns.'),('Reward earnings','Not available','Data gap','Requires a verified reward credits/earnings transaction table.'),('Withdrawal completion time','Not available','Data gap','Requires withdrawal requests, status history, and timestamps.'),('Referral conversion rate','Not available','Data gap','Requires invite, signup, and attribution events.'),('Retention by cohort','Not available','Data gap','Requires reliable event-level activity history and cohort rules.')]
    return render_template_string(template,nav=NAV,page='kpis',title='KPI catalogue',kpis=items)
@app.route('/insights')
@login_required
def insights():
    df=get_df(); groups=[('Acquisition distribution',counts(df,find_col(df,'acquisition_source','acquisition_channel'))),('Account status',counts(df,find_col(df,'account_status'))),('Device distribution',counts(df,find_col(df,'primary_device','device_type')))]
    groups=[(n,v) for n,v in groups if v]
    return render_template_string(template,nav=NAV,page='insights',title='Insights & gaps',groups=groups)
@app.route('/backlog')
@login_required
def backlog():
    items=[('P1','Validate source fields and date rules','Confirm data dictionary, timezone, date formats, and missing-value treatment.','Data / Analytics'),('P1','Add event-level tracking','Capture task, reward, referral, wallet, and withdrawal events with timestamps and stable IDs.','Product / Engineering'),('P1','Define KPI calculation rules','Document numerator, denominator, event window, exclusions, and refresh cadence.','Analytics'),('P2','Build verified transaction tables','Separate reward credits, wallet ledger entries, withdrawals, reversals, and payout outcomes.','Backend / Data'),('P2','Create QA checks','Add duplicate, schema, freshness, null, referential integrity, and date-order checks.','Data Engineering'),('P3','Automate refresh and monitoring','Schedule refreshes and alert on failed loads or unexpected metric changes.','Data Engineering')]
    return render_template_string(template,nav=NAV,page='backlog',title='Action backlog',items=items)
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    f = request.files.get('dataset')
    if not f or not f.filename:
        flash('Choose a CSV or Excel file first.', 'error')
        return redirect(url_for('dashboard'))
    filename = f.filename.lower()
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(f)
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(f)
        else:
            flash('Unsupported file. Please upload CSV or Excel.', 'error')
            return redirect(url_for('dashboard'))
        if df.empty or len(df.columns) == 0:
            raise ValueError('empty dataset')
        user_active = os.path.join(DATA, f'user_{current_user.get_id()}_active.csv')
        df.to_csv(user_active, index=False)
        flash(f'Dataset loaded: {len(df):,} rows and {len(df.columns)} columns. Server uploads may be lost if the hosting filesystem is reset.', 'success')
    except Exception:
        flash('Could not read this file. Check the format and try again.', 'error')
    return redirect(url_for('dashboard'))

@app.route('/reset', methods=['POST'])
@login_required
def reset():
    user_active = os.path.join(DATA, f'user_{current_user.get_id()}_active.csv')
    if os.path.exists(user_active):
        os.remove(user_active)
    flash('Restored the included sample dataset for your account.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/download')
@login_required
def download():
    return send_file(data_path(), as_attachment=True, download_name='velop_users.csv')

@app.route('/api/summary')
@login_required
def api_summary(): return jsonify(summary(get_df()))
@app.route('/health')
def health(): return jsonify({'status':'ok','service':'VELOOP Consolidated Analytics Portal'})
if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=os.environ.get('FLASK_DEBUG','false').lower()=='true')
