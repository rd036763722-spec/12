import os, sys, json, re, time, base64, shutil, threading, subprocess, webbrowser, socket, secrets, string
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
try:
    import webview
except Exception:
    webview = None
W = {'main': None, 'br': None}

APPDIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'ChromeServerWizard')
os.makedirs(APPDIR, exist_ok=True)
SF = os.path.join(APPDIR, 'state.json')
ST = {'ip': '', 'key': '', 'link': '', 'pw': '', 'ad_id': ''}
try:
    ST.update(json.load(open(SF, encoding='utf-8')))
except Exception:
    pass
NW = 0x08000000 if os.name == 'nt' else 0
J = {'lines': [], 'running': False, 'code': None}
LAST = {'ping': 0}


def save():
    d = {k: v for k, v in ST.items() if k != 'pw'}
    try:
        json.dump(d, open(SF, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass


def log(s):
    J['lines'].append(s)


def ssh_base():
    return ['ssh', '-i', ST['key'], '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ServerAliveInterval=20',
            '-o', 'ConnectTimeout=25', '-o', 'BatchMode=yes', 'ubuntu@' + ST['ip']]


def run_remote(script):
    b = base64.b64encode(script.encode()).decode()
    cmd = ssh_base() + ['bash <(echo %s | base64 -d) </dev/null 2>&1' % b]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NW,
                         encoding='utf-8', errors='replace')
    for line in p.stdout:
        line = line.rstrip()
        m = re.match(r'^ANYDESK_ID=(\d{6,})$', line)
        if m:
            ST['ad_id'] = m.group(1)
        log(line)
    return p.wait()


def ssh_ok():
    try:
        r = subprocess.run(ssh_base() + ['echo ok'], capture_output=True, timeout=45, creationflags=NW)
        return r.returncode == 0
    except Exception:
        return False


S_DESK = '''set -e
sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get -o DPkg::Lock::Timeout=300 update
sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get -o DPkg::Lock::Timeout=300 install -y xfce4 lightdm dbus-x11 xserver-xorg-video-dummy
sudo systemctl set-default graphical.target'''
S_CHR = 'set -e\nsudo snap install chromium'
S_AUTO = '''set -e
sudo mkdir -p /etc/lightdm/lightdm.conf.d /etc/X11/xorg.conf.d
printf '[Seat:*]\\nautologin-user=ubuntu\\nautologin-user-timeout=0\\nautologin-session=xfce\\n' | sudo tee /etc/lightdm/lightdm.conf.d/50-autologin.conf >/dev/null
sudo tee /etc/X11/xorg.conf.d/10-dummy.conf >/dev/null <<'EOF'
Section "Device"
  Identifier "d"
  Driver "dummy"
  VideoRam 256000
EndSection
Section "Screen"
  Identifier "s"
  Device "d"
  DefaultDepth 24
  SubSection "Display"
    Depth 24
    Modes "1920x1080"
  EndSubSection
EndSection
EOF
echo "הוגדרו כניסה אוטומטית ומסך וירטואלי"'''
S_ADI = '''set -e
wget -q -O anydesk.deb "%s"
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y ./anydesk.deb'''
S_ADB = '''set -e
sudo systemctl enable anydesk
mkdir -p ~/.config/autostart
printf '[Desktop Entry]\\nType=Application\\nName=AnyDesk\\nExec=anydesk --tray\\n' > ~/.config/autostart/anydesk.desktop
nohup bash -c 'sleep 3; sudo reboot' >/dev/null 2>&1 &
echo "השרת מופעל מחדש..."'''
S_ADP = '''ID=""
for i in $(seq 1 15); do ID=$(anydesk --get-id 2>/dev/null | tail -n1); case "$ID" in ''|*[!0-9]*) sleep 6;; *) break;; esac; done
echo "%s" | sudo anydesk --set-password
echo "ANYDESK_ID=$ID"'''


def check_base():
    if not shutil.which('ssh'):
        log('לא נמצא ssh במחשב. ב-Windows 10/11: הגדרות > אפליקציות > תכונות אופציונליות > OpenSSH Client.')
        return False
    if not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ST['ip']) or not os.path.isfile(ST['key']):
        log('חסרה כתובת IP תקינה או קובץ מפתח.')
        return False
    if os.name == 'nt':
        subprocess.run(['icacls', ST['key'], '/inheritance:r', '/grant:r', os.environ.get('USERNAME', '') + ':R'],
                       capture_output=True, creationflags=NW)
    return True


def seq(items):
    for title, script in items:
        log('\n=== ' + title + ' ===')
        c = run_remote(script)
        if c != 0:
            log('נכשל (קוד %d). אפשר ללחוץ שוב להרצה חוזרת.' % c)
            return c
    return 0


def j_connect():
    if not check_base():
        return 1
    log('מתחבר ל-%s ...' % ST['ip'])
    c = run_remote('echo "מחובר כ: $(whoami)"; uname -m; free -h | head -2')
    if c != 0:
        log('החיבור נכשל. בדוק IP וקובץ מפתח, ונסה ממחשב/רשת בלי סינון.')
    return c


def j_prep():
    if not check_base():
        return 1
    return seq([('2.2 שולחן עבודה', S_DESK), ('2.3 דפדפן', S_CHR), ('2.4 כניסה אוטומטית ומסך וירטואלי', S_AUTO)])


def j_ad_pw():
    if not check_base():
        return 1
    if not re.match(r'^[A-Za-z0-9]{10,}$', ST['pw']):
        log('הסיסמה חייבת להיות באותיות לועזיות ומספרים בלבד, 10 תווים לפחות.')
        return 1
    c = run_remote(S_ADP % ST['pw'])
    return c if c else (0 if ST['ad_id'] else 1)


def j_ad_all():
    if not check_base():
        return 1
    if not re.match(r'^https://[^\s"\']+$', ST['link']):
        log('הדבק קישור הורדה תקין (מתחיל ב-https://).')
        return 1
    c = seq([('3.1 התקנת AnyDesk', S_ADI % ST['link']), ('3.2 הפעלה אוטומטית והפעלה מחדש', S_ADB)])
    if c:
        return c
    log('\nממתין שהשרת יעלה מחדש (כשתי דקות)...')
    time.sleep(45)
    for _ in range(25):
        if ssh_ok():
            break
        time.sleep(8)
    else:
        log('השרת לא חזר. נסה "הגדר קוד וסיסמה" בעוד דקה.')
        return 1
    log('\n=== 3.3 קוד וסיסמה קבועים ===')
    return j_ad_pw()


JOBS = {'connect': j_connect, 'prep': j_prep, 'ad_all': j_ad_all, 'ad_pw': j_ad_pw}


def job_thread(name):
    try:
        J['code'] = JOBS[name]()
    except Exception as e:
        log('שגיאה: ' + str(e))
        J['code'] = 1
    save()
    J['running'] = False


TOOLBAR = r"""(function(){
function add(){if(document.getElementById('__wz')||!document.documentElement)return;
var b=document.createElement('div');b.id='__wz';var s=b.style;s.position='fixed';s.top='0';s.left='0';s.right='0';s.height='38px';s.background='#0f766e';s.zIndex='2147483647';s.display='flex';s.alignItems='center';s.gap='6px';s.padding='0 10px';s.direction='ltr';
function mk(t,f){var x=document.createElement('button');x.textContent=t;var y=x.style;y.border='0';y.background='#0b5a54';y.color='#fff';y.borderRadius='6px';y.padding='4px 12px';y.cursor='pointer';y.font='15px Segoe UI,Arial';x.onclick=f;b.appendChild(x)}
mk('\u2039',function(){history.back()});mk('\u203a',function(){history.forward()});mk('\u27f3',function(){location.reload()});
var l=document.createElement('span');l.textContent=location.hostname;l.style.color='#fff';l.style.font='13px Segoe UI,Arial';l.style.marginLeft='8px';b.appendChild(l);
document.documentElement.appendChild(b);document.documentElement.style.marginTop='38px';}
add();if(!window.__wzi){window.__wzi=1;setInterval(add,1500);}})();"""


def screen_size():
    try:
        sc = webview.screens[0]
        return int(sc.width), int(sc.height)
    except Exception:
        return 1920, 1080


def open_url(url):
    if not webview or not W['main']:
        webbrowser.open(url)
        return
    br = W['br']
    if br is not None:
        try:
            br.load_url(url)
            return
        except Exception:
            W['br'] = None
    sw, sh = screen_size()
    try:
        W['main'].move(int(sw * 0.55), 0)
        W['main'].resize(int(sw * 0.45), sh - 60)
    except Exception:
        pass
    br = webview.create_window('דפדפן האשף', url, x=0, y=0, width=int(sw * 0.55), height=sh - 60)
    br.events.loaded += lambda: br.evaluate_js(TOOLBAR)
    br.events.closed += lambda: W.__setitem__('br', None)
    W['br'] = br


def pick():
    if webview and W['main']:
        try:
            kind = webview.FileDialog.OPEN if hasattr(webview, 'FileDialog') else webview.OPEN_DIALOG
            r = W['main'].create_file_dialog(kind, directory=os.path.join(os.path.expanduser('~'), 'Downloads'))
            return os.path.normpath(r[0]) if r else ''
        except Exception:
            pass
    return _pick_tk()


def _pick_tk():
    import tkinter as tk
    from tkinter import filedialog
    r = tk.Tk()
    r.withdraw()
    r.attributes('-topmost', True)
    p = filedialog.askopenfilename(title='בחר את קובץ המפתח הפרטי (.key)',
                                   initialdir=os.path.join(os.path.expanduser('~'), 'Downloads'))
    r.destroy()
    return os.path.normpath(p) if p else ''


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, ctype='application/json'):
        b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/':
            return self.send(HTML.encode('utf-8'), 'text/html')
        if u.path == '/api/ping':
            LAST['ping'] = time.time()
            return self.send({'ok': 1})
        if u.path == '/api/state':
            return self.send(ST)
        if u.path == '/api/log':
            n = int(parse_qs(u.query).get('from', ['0'])[0])
            ls = J['lines'][n:]
            return self.send({'lines': ls, 'n': n + len(ls), 'done': not J['running'], 'code': J['code'],
                              'state': {'ad_id': ST['ad_id']}})
        self.send({})

    def do_POST(self):
        ln = int(self.headers.get('Content-Length', 0))
        d = json.loads(self.rfile.read(ln) or b'{}')
        p = urlparse(self.path).path
        if p == '/api/state':
            for k in ST:
                if k in d:
                    ST[k] = str(d[k]).strip()
            save()
            return self.send({'ok': 1})
        if p == '/api/open':
            if str(d.get('url', '')).startswith('https://'):
                open_url(d['url'])
            return self.send({'ok': 1})
        if p == '/api/pick':
            return self.send({'path': pick()})
        if p == '/api/run':
            if J['running']:
                return self.send({'error': 'פעולה אחרת עדיין רצה'})
            if d.get('job') not in JOBS:
                return self.send({'error': 'לא ידוע'})
            J.update(lines=[], running=True, code=None)
            threading.Thread(target=job_thread, args=(d['job'],), daemon=True).start()
            return self.send({'ok': 1})
        self.send({})


def find_browser():
    pf = [os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('PROGRAMFILES', ''), os.environ.get('LOCALAPPDATA', '')]
    for rel in [r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe']:
        for b in pf:
            if b and os.path.isfile(os.path.join(b, rel)):
                return os.path.join(b, rel)
    return shutil.which('msedge') or shutil.which('chrome') or shutil.which('google-chrome') or shutil.which('chromium')


def main():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:%d/' % port
    if webview:
        try:
            webview.settings['ALLOW_DOWNLOADS'] = True
        except Exception:
            pass
        W['main'] = webview.create_window('כרום על שרת חינמי', url, width=1100, height=820)
        W['main'].events.closed += lambda: os._exit(0)
        webview.start()
        return
    br = find_browser()
    if br:
        subprocess.Popen([br, '--app=' + url, '--window-size=1150,860'])
    else:
        webbrowser.open(url)
    t0 = time.time()
    while True:
        time.sleep(3)
        if LAST['ping'] and time.time() - LAST['ping'] > 90 and not J['running']:
            break
        if not LAST['ping'] and time.time() - t0 > 60:
            break


HTML = r'''<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>כרום על שרת חינמי</title>
<style>
:root{--g:#0f766e;--gd:#0b5a54;--bg:#f0f2f3;--bd:#d9dee1;--tx:#1b2328;--mu:#6b767d}
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Arial,sans-serif;background:var(--bg);color:var(--tx);display:flex;flex-direction:column;height:100vh}
header{background:#fff;padding:18px 28px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--bd)}
header h1{margin:0;font-size:22px}header p{margin:2px 0 0;color:var(--mu);font-size:14px}.logo{font-size:34px;color:var(--g)}
nav{background:#fff;padding:12px 24px;display:flex;flex-wrap:wrap;gap:8px;border-bottom:1px solid var(--bd)}
.pill{display:flex;align-items:center;gap:8px;border:1px solid var(--bd);background:#fff;border-radius:999px;padding:6px 14px 6px 10px;font:inherit;font-size:14px;color:var(--mu);cursor:pointer}
.pill b{width:24px;height:24px;border-radius:50%;background:#e6eaec;display:grid;place-items:center;font-size:13px;color:var(--mu)}
.pill.on{border:2px solid var(--g);color:var(--tx);font-weight:600}.pill.on b{background:var(--g);color:#fff}
.pill.ok b{background:#cfe9e5;color:var(--g)}
main{flex:1;overflow:auto;padding:22px 28px}.card{background:#fff;border:1px solid var(--bd);border-radius:12px;padding:26px 32px;max-width:900px;margin:auto}
h2{margin:0 0 14px;font-size:28px}p,li{line-height:1.7;font-size:16px}ul,ol{padding-inline-start:22px}
.call{border-radius:8px;padding:10px 14px;margin:14px 0;font-size:15px}.warn{background:#fcefd9;border:1px solid #f0d9a8}.tip{background:#e3eff7;border:1px solid #c5dcec}.good{background:#e0f1e6;border:1px solid #bddfc8}
.btn,footer button{font:inherit;font-size:15px;padding:9px 20px;border-radius:8px;border:1px solid var(--g);background:#fff;color:var(--g);cursor:pointer;margin:4px 0 4px 8px}
.btn.pri,footer .pri{background:var(--g);color:#fff;font-weight:600}.btn:disabled{opacity:.5;cursor:wait}
input[type=text]{width:100%;font:inherit;padding:9px 12px;border:1px solid var(--bd);border-radius:8px;direction:ltr;text-align:left}
label{display:block;margin:14px 0 4px;font-weight:600;font-size:15px}.row{display:flex;gap:8px;align-items:center}
.log{display:none;background:#14191c;color:#d6e3e8;direction:ltr;text-align:left;border-radius:8px;padding:12px;height:230px;overflow:auto;font:12.5px Consolas,monospace;white-space:pre-wrap;margin-top:12px}
.st{margin-top:8px;font-weight:600}.st.ok{color:var(--g)}.st.bad{color:#b3261e}
code{background:#eef1f2;padding:2px 6px;border-radius:5px;direction:ltr;unicode-bidi:embed;font-size:14px}
table{border-collapse:collapse;width:100%}td{padding:8px;border-bottom:1px solid var(--bd)}td:last-child{direction:ltr;text-align:left;font-family:Consolas,monospace}
details{border:1px solid var(--bd);border-radius:8px;padding:8px 14px;margin:8px 0}summary{cursor:pointer;font-weight:600}
footer{background:#fff;border-top:1px solid var(--bd);padding:12px 28px;display:flex;justify-content:space-between}footer small{color:var(--mu);align-self:center}
</style></head><body>
<header><div><h1>כרום על שרת חינמי</h1><p>אשף התקנה אוטומטי · Oracle + AnyDesk</p></div><div class="logo">☁</div></header>
<nav id="nav"></nav><main><section class="card" id="card"></section></main>
<footer><button onclick="go(cur-1)" id="prev">→ הקודם</button><small id="ft"></small><div><button class="pri" onclick="nxt()" id="next">הבא ←</button><button onclick="go(cur+1)" id="skip" title="מעבר לשלב הבא בלי בדיקות">דלג ⇠</button></div></footer>
<script>
const $=s=>document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
const api=(p,b)=>fetch('/api/'+p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})}).then(r=>r.json());
let S={ip:'',key:'',link:'',pw:'',ad_id:''},cur=0,done={},busy=false,LOG={},MSG={};
const JS={connect:3,prep:4,ad_all:5,ad_pw:5};
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
const call=(t,x)=>`<div class="call ${t}">${x}</div>`;
const op=(u,l)=>`<button class="btn" onclick="api('open',{url:'${u}'})">${l} ↗</button>`;
const cp=(v,l)=>`<button class="btn" onclick="navigator.clipboard.writeText('${esc(v)}')">${l||'העתק'}</button>`;
const lb=i=>`<pre class="log" id="log" ${LOG[i]!=null?'style="display:block"':''}>${esc(LOG[i]||'')}</pre><div id="st" class="st ${MSG[i]?MSG[i][0]:''}">${MSG[i]?MSG[i][1]:''}</div>`;
const fld=(k,l,ph)=>`<label>${l}</label><input type="text" value="${esc(S[k])}" placeholder="${ph||''}" oninput="S.${k}=this.value.trim()">`;
const s0=()=>`<p>הדפדפן לא רץ על המחשב שלכם אלא על שרת מרוחק: אתם רק רואים את המסך שלו ומקלידים. הגלישה יוצאת מהשרת ולא מהחיבור שלכם.</p>
<p>האשף ילווה אתכם שלב אחר שלב, ויריץ בעצמו את כל פקודות ההתקנה בשרת.</p>
<ul><li>זמן: כ-20 דקות</li><li>כרטיס אשראי לאימות בלבד, בלי חיוב</li><li>Windows 10/11 עם OpenSSH Client (מותקן כברירת מחדל)</li></ul>
${call('warn','<b>חשוב:</b> שלבים 2 עד 6 עושים פעם אחת בלבד ממחשב בלי סינון (ייתכן שהסינון חוסם את אתר Oracle). אחר כך מתחברים מכל מחשב, גם מסונן. בדקו מראש ש-AnyDesk פועל במחשב המסונן.')}`;
const s1=()=>`<ol><li>נכנסים ל-<code>oracle.com/cloud/free</code> ולוחצים <code>Start for free</code>.</li><li>ממלאים פרטים (כרטיס אשראי לאימות בלבד, בלי חיוב).</li><li>ב-<code>Home Region</code> בוחרים אזור באירופה, למשל <code>Frankfurt</code> או <code>Amsterdam</code>.</li></ol>
${call('warn','<b>שימו לב:</b> את האזור אי אפשר לשנות אחר כך.')}${op('https://www.oracle.com/cloud/free/','פתח את Oracle')}`;
const s2=()=>`<p>בקונסולה: <code>☰ &gt; Compute &gt; Instances &gt; Create instance</code> ואז ממלאים:</p><ul>
<li><b>Name:</b> chrome</li><li><b>Image:</b> Change image ואז Ubuntu 22.04 או 24.04 (לא Minimal)</li>
<li><b>Shape:</b> Change shape &gt; Ampere, מסמנים VM.Standard.A1.Flex ומגדירים 4 OCPU ו-24GB (או 2 OCPU ו-12GB)</li>
<li><b>Networking:</b> ודאו ש-Assign a public IPv4 address מסומן</li><li><b>SSH keys:</b> Generate a key pair for me ואז <b>Save private key</b></li></ul>
${op('https://cloud.oracle.com/compute/instances','פתח את קונסולת Oracle')}
${call('warn','<b>שימו לב:</b> קובץ המפתח הפרטי חייב להישמר. בלעדיו אי אפשר להתחבר לשרת.')}
${call('tip','<b>טיפ:</b> קיבלתם Out of capacity? נסו שוב כל כמה דקות, או הקטינו ל-2 ליבות ו-12GB.')}
<p>אחרי כדקה הסטטוס הופך ל-Running והכתובת Public IP מופיעה. מזינים אותה כאן ובוחרים את קובץ המפתח:</p>
${fld('ip','כתובת IP של השרת','לדוגמה 130.61.10.20')}<label>קובץ המפתח הפרטי</label>
<div class="row"><input type="text" id="key" value="${esc(S.key)}" readonly placeholder="לא נבחר קובץ"><button class="btn" style="white-space:nowrap" onclick="pick()">בחר קובץ…</button></div>`;
const s3=()=>`<p>האשף יתחבר לשרת עם <code>ssh -i KEY ubuntu@${esc(S.ip||'IP')}</code> וידאג אוטומטית להרשאות הקובץ (פותר שגיאת UNPROTECTED PRIVATE KEY FILE).</p>
<button class="btn pri act" onclick="run('connect')">בדוק חיבור</button>
${call('good','<b>הצלחה:</b> תופיע שורה "מחובר כ: ubuntu". אם נתקע, כנראה הרשת חוסמת SSH, נסו ממחשב או טלפון בלי סינון.')}${lb(3)}`;
const s4=()=>`<p>הכפתור יתקין בשרת ברצף:</p><ol><li>שולחן עבודה XFCE (2.2) — לוקח כמה דקות</li><li>דפדפן Chromium (2.3). בשרת ARM אין Google Chrome רשמי, ו-Chromium כמעט זהה.</li><li>כניסה אוטומטית ומסך וירטואלי (2.4). בלעדיו AnyDesk מציג מסך שחור.</li></ol>
<button class="btn pri act" onclick="run('prep')">התקן הכול</button>${lb(4)}`;
const s5=()=>`<p>דרוש קישור להורדת AnyDesk: ב-<code>anydesk.com</code>, דף ההורדות של לינוקס, בוחרים חבילת <b>DEB</b> מסוג <b>ARM 64-bit</b>, קליק ימני עליה ו-<code>Copy link address</code>.</p>${op('https://anydesk.com/en/downloads/linux','פתח את דף ההורדות')}
${fld('link','קישור DEB (ARM 64-bit)','https://download.anydesk.com/...')}
<label>סיסמה קבועה (אותיות לועזיות ומספרים בלבד, 10+ תווים)</label>
<div class="row"><input type="text" id="pw" value="${esc(S.pw)}" oninput="S.pw=this.value.trim()"><button class="btn" style="white-space:nowrap" onclick="genpw()">צור סיסמה</button></div>
<button class="btn pri act" onclick="run('ad_all')">התקן והגדר</button><button class="btn act" onclick="run('ad_pw')">רק קוד וסיסמה</button>
${call('tip','השרת יופעל מחדש באמצע, והחלון ימתין לו לבד (כשתי דקות).')}${lb(5)}
${S.ad_id?call('good','<b>ה-ID הקבוע של השרת:</b> <code>'+S.ad_id+'</code> '+cp(S.ad_id)):''}`;
const s6=()=>`<p>שלב זה אפשר לעשות מכל מחשב, גם מהמחשב המסונן.</p><ol><li>נכנסים ל-<code>anydesk.com</code>, מורידים ומפעילים AnyDesk ל-Windows או ל-Mac (בלי הרשמה).</li>
<li>בשדה הכתובת מקלידים את ה-ID של השרת, לוחצים Connect ומזינים את הסיסמה.</li><li>אחרי כמה שניות מופיע שולחן העבודה של השרת.</li></ol>${op('https://anydesk.com/en/downloads','הורד AnyDesk')}
<table><tr><td>ID</td><td>${esc(S.ad_id||'—')} ${S.ad_id?cp(S.ad_id):''}</td></tr><tr><td>סיסמה</td><td>${esc(S.pw||'—')} ${S.pw?cp(S.pw):''}</td></tr></table>`;
const s7=()=>`<p><b>בדיקה:</b> בשולחן העבודה של השרת בוחרים בתפריט היישומים (בפינה העליונה) Internet &gt; Chromium, ובגוגל מחפשים <code>what is my IP</code>.</p>
${call('good','<b>הצלחה:</b> מופיעה כתובת של Oracle ולא הכתובת שלכם. אתם גולשים דרך השרת! אם איטי, הנמיכו איכות ב-Display &gt; Quality.')}
<h3>מה לשמור</h3><table><tr><td>כתובת IP</td><td>${esc(S.ip)}</td></tr><tr><td>קובץ מפתח</td><td>${esc(S.key)}</td></tr><tr><td>AnyDesk ID</td><td>${esc(S.ad_id)}</td></tr><tr><td>סיסמה</td><td>${esc(S.pw)}</td></tr></table>
${call('warn','מי שיש לו את ה-ID והסיסמה יכול להיכנס לשרת. אין לשתף אותם. Oracle רשאית לאסוף חזרה מכונות חינמיות שאינן בשימוש, לכן השתמשו בשרת מדי פעם. אל תחרגו מ-4 OCPU ו-24GB.')}
<h3>משהו לא עובד?</h3>
<details><summary>AnyDesk מתחבר אבל המסך שחור</summary>הריצו שוב את שלב "הכנת השרת", ואז הפעילו מחדש את השרת מקונסולת Oracle (Reboot).</details>
<details><summary>ה-ID לא מתחבר / השרת לא זמין</summary>הפעילו מחדש את השרת מקונסולת Oracle, והמתינו כשתי דקות.</details>
<details><summary>הסיסמה לא מתקבלת</summary>חזרו לשלב "AnyDesk בשרת" והריצו "רק קוד וסיסמה" עם סיסמה חדשה.</details>
<details><summary>AnyDesk נחסם במחשב המסונן</summary>אם הרשת חוסמת את AnyDesk עצמו, השיטה לא תעבוד ברשת הזו.</details>`;
const STEPS=[['ברוכים הבאים',s0],['חשבון Oracle',s1],['יצירת השרת',s2],['חיבור לשרת',s3],['הכנת השרת',s4],['AnyDesk בשרת',s5],['AnyDesk במחשב',s6],['בדיקה וסיום',s7]];
function render(){
 $('#nav').innerHTML=STEPS.map((s,i)=>`<button class="pill ${i==cur?'on':''} ${done[i]?'ok':''}" onclick="go(${i})"><b>${done[i]&&i!=cur?'✓':i+1}</b>${s[0]}</button>`).join('');
 $('#card').innerHTML=`<h2>${STEPS[cur][0]}</h2>`+STEPS[cur][1]();
 $('#prev').style.visibility=cur?'visible':'hidden';$('#next').style.visibility=$('#skip').style.visibility=cur<STEPS.length-1?'visible':'hidden';
 $('#ft').textContent=`שלב ${cur+1} מתוך ${STEPS.length}`;
 document.querySelectorAll('.act').forEach(b=>b.disabled=busy);
}
const save=()=>api('state',S);
function go(i){if(i<0||i>=STEPS.length)return;save();cur=i;render()}
function nxt(){
 const need={2:!S.ip||!S.key?'הזינו כתובת IP ובחרו קובץ מפתח':'',3:!done[3]?'החיבור לשרת עדיין לא נבדק בהצלחה':'',4:!done[4]?'ההתקנה בשרת עדיין לא הסתיימה בהצלחה':'',5:!S.ad_id?'ה-ID של AnyDesk עדיין לא התקבל':''}[cur];
 if(need&&!confirm(need+'. להמשיך בכל זאת?'))return;
 done[cur]=true;go(cur+1);
}
async function pick(){const r=await api('pick');if(r.path){S.key=r.path;await save();render()}}
function genpw(){const c='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';S.pw=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>c[x%c.length]).join('');render()}
async function run(name){
 if(busy)return;const step=JS[name];
 if(!S.ip||!S.key){alert('חזרו לשלב "יצירת השרת" והזינו IP וקובץ מפתח');return}
 if(name=='ad_all'&&!S.link){alert('הדביקו קישור הורדה של AnyDesk');return}
 if((name=='ad_all'||name=='ad_pw')&&!/^[A-Za-z0-9]{10,}$/.test(S.pw)){alert('סיסמה: אותיות לועזיות ומספרים בלבד, 10 תווים לפחות');return}
 await save();busy=true;LOG[step]='';MSG[step]=['','רץ... נא להמתין'];render();$('#log').style.display='block';
 const r=await api('run',{job:name});if(r.error){busy=false;LOG[step]=r.error;MSG[step]=['bad','שגיאה'];render();return}
 let n=0;
 while(true){await sleep(800);const d=await (await fetch('/api/log?from='+n)).json();
  if(d.lines.length){LOG[step]+=d.lines.join('\n')+'\n';n=d.n;if(cur==step){const l=$('#log');l.textContent=LOG[step];l.scrollTop=l.scrollHeight}}
  if(d.done){busy=false;S.ad_id=d.state.ad_id||S.ad_id;const ok=d.code==0;done[step]=ok||done[step];
   MSG[step]=ok?['ok','✓ הושלם בהצלחה']:['bad','✗ נכשל — עיינו בלוג ונסו שוב'];break}}
 render();const l=$('#log');if(l){l.scrollTop=l.scrollHeight}
}
fetch('/api/state').then(r=>r.json()).then(s=>{S=Object.assign(S,s);if(S.ad_id)done[5]=false;render()});
setInterval(()=>fetch('/api/ping'),5000);fetch('/api/ping');
</script></body></html>'''

if __name__ == '__main__':
    main()
