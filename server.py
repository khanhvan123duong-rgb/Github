from flask import Flask, render_template_string, request, session, redirect, jsonify, send_file
import json
import os
import random
import string
import time
import hashlib
import collections
import re
import shutil
from datetime import datetime, timezone, timedelta
try:
    import requests as _req_tg
    _TG_OK = True
except ImportError:
    _req_tg = None
    _TG_OK = False

  
app = Flask(__name__)
app.secret_key = 'server_key_bi_mat_2026_vinhvien'
app.permanent_session_lifetime = timedelta(days=365)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    return response

# --- GLOBAL OPTIONS HANDLER (fix CORS preflight for all routes) ---
@app.before_request
def handle_options():
    # Xử lý CORS preflight (OPTIONS) cho tất cả routes
    if request.method == 'OPTIONS':
        from flask import make_response
        resp = make_response('', 204)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        return resp

# --- HEALTH CHECK ENDPOINT ---
@app.route('/healthz')
def healthz():
    return jsonify({"status": "ok", "db": os.path.exists(DB_FILE)}), 200

# --- KEEP-ALIVE: self-ping every 14 minutes to reduce cold starts ---
import threading, urllib.request as _ureq, urllib.parse

def _keep_alive_worker():
    import time as _time
    _time.sleep(60)  # wait for server to fully start
    while True:
        _time.sleep(14 * 60)
        try:
            host = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host:
                _ureq.urlopen(host.rstrip('/') + '/healthz', timeout=10)
        except Exception:
            pass

_ka_thread = threading.Thread(target=_keep_alive_worker, daemon=True)
_ka_thread.start()

# ---- EXTRA KEEP-ALIVE #2: additional self-ping every 14 minutes (offset 7 min) ----
def _keep_alive_worker2():
    import time as _t2
    _t2.sleep(420)  # 7-minute offset from first pinger
    while True:
        _t2.sleep(14 * 60)
        try:
            host2 = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host2:
                _ureq.urlopen(host2.rstrip('/') + '/healthz', timeout=10)
        except Exception:
            pass

_ka_thread2 = threading.Thread(target=_keep_alive_worker2, daemon=True)
_ka_thread2.start()

# ---- EXTRA KEEP-ALIVE #3: third self-ping every 14 minutes (offset ~4.5 min) ----
def _keep_alive_worker3():
    import time as _t3
    _t3.sleep(270)  # 4.5-minute offset — fills gap between worker1 and worker2
    while True:
        _t3.sleep(14 * 60)
        try:
            host3 = os.environ.get('RENDER_EXTERNAL_URL', '')
            if host3:
                _ureq.urlopen(host3.rstrip('/') + '/healthz', timeout=10)
        except Exception:
            pass

_ka_thread3 = threading.Thread(target=_keep_alive_worker3, daemon=True)
_ka_thread3.start()
# With 3 pingers (offsets: 0, 7min, 4.5min) each cycling every 14min,
# the server gets pinged roughly every ~4.5 minutes — well within Render's 15-min sleep threshold.



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use Render persistent disk if available, otherwise fall back to script directory
DATA_DIR = '/data' if os.path.isdir('/data') else BASE_DIR
DB_FILE = os.path.join(DATA_DIR, "database_keys.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
VN_TZ = timezone(timedelta(hours=7))

# --- REAL IP FROM SERVER ---
def get_real_ip():
    if request.headers.get('CF-Connecting-IP'): return request.headers.get('CF-Connecting-IP')
    if request.headers.get('X-Forwarded-For'): return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

# --- DATABASE ENGINE ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {"___ADMIN_CONFIG___": {"user": "vkhanh", "pass": "1"}}
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            if "___ADMIN_CONFIG___" not in data:
                data["___ADMIN_CONFIG___"] = {"user": "vkhanh", "pass": "1"}
            return data
        except:
            return {"___ADMIN_CONFIG___": {"user": "vkhanh", "pass": "1"}}

def save_db(data):
    tmp = DB_FILE + '.tmp'
    bak = DB_FILE + '.bak'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        if os.path.exists(DB_FILE):
            shutil.copy2(DB_FILE, bak)
        os.replace(tmp, DB_FILE)
    except Exception as e:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

def get_time_left_str(expiry_timestamp):
    if expiry_timestamp == -1: return "∞"
    now = time.time()
    diff = expiry_timestamp - now
    if diff <= 0: return "Hết hạn"
    days = int(diff // 86400)
    hours = int((diff % 86400) // 3600)
    minutes = int((diff % 3600) // 60)
    parts = []
    if days > 0: parts.append(f"{days} ngày")
    if hours > 0: parts.append(f"{hours} giờ")
    if minutes > 0: parts.append(f"{minutes} phút")
    return " ".join(parts) if parts else "Dưới 1 phút"

def format_ts(ts):
    if not ts: return "Chưa cập nhật"
    return datetime.fromtimestamp(ts, VN_TZ).strftime('%d/%m/%Y %H:%M:%S')

def format_full_ts(ts):
    if not ts: return "Chưa kích hoạt"
    dt = datetime.fromtimestamp(ts, VN_TZ)
    days = ["Chủ Nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"]
    day_str = days[int(dt.strftime('%w'))]
    return f"{day_str}, {dt.strftime('%d/%m/%Y %H:%M:%S')} (VN)"

# --- ROUTES ---
@app.route('/nhac.mp3')
def play_music():
    f = os.path.join(BASE_DIR, 'nhac.mp3')
    if os.path.exists(f): return send_file(f, mimetype='audio/mp3')
    return jsonify({"status": "missing"}), 404

@app.route('/nhac2.mp3')
def play_music2():
    f = os.path.join(BASE_DIR, 'nhac2.mp3')
    if os.path.exists(f): return send_file(f, mimetype='audio/mp3')
    return jsonify({"status": "missing"}), 404

@app.route('/nhac3.mp3')
def play_music3():
    f = os.path.join(BASE_DIR, 'nhac3.mp3')
    if os.path.exists(f): return send_file(f, mimetype='audio/mp3')
    return jsonify({"status": "missing"}), 404

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        k = request.form.get('key', '').strip()
        db = load_db()
        if k in db and not k.startswith("___"):
            info = db[k]
            now = time.time()
            if isinstance(info.get('used_devices', []), list):
                new_devs = {}
                for d in info.get('used_devices', []): new_devs[d] = info.get('expiry_time', 0)
                info['used_devices'] = new_devs
                save_db(db)
            if info['status'] == 'Đã kích hoạt':
                is_full = len(info['used_devices']) >= info['max_devices']
                _non_perm = [e for e in info['used_devices'].values() if e != -1]
                all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
                if is_full and all_exp:
                    info['status'] = "Hết hạn"
                    save_db(db)
            return jsonify({
                "exists": True, "key": k, "key_status": info['status'],
                "duration": f"{info['duration_val']} {info['duration_unit']}" if info['duration_unit'] != 'permanent' else "Vĩnh viễn",
                "max_devices": info['max_devices'], "used_devices": len(info['used_devices']),
                "created_at": format_ts(info.get('created_at', 0)),
                "activated_time": format_ts(info.get('activated_time')) if info.get('activated_time') else "Chưa kích hoạt",
                "dev_dict": info['used_devices']
            })
        return jsonify({"exists": False, "msg": "Mã Key không tồn tại trên hệ thống máy chủ!"})
    return render_template_string(UI_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    db = load_db()
    admin_cfg = db.get("___ADMIN_CONFIG___", {"user": "vkhanh", "pass": "1"})
    if request.form.get('user') == admin_cfg['user'] and request.form.get('pass') == admin_cfg['pass']:
        session.clear()
        session.permanent = True
        session['is_admin'] = True
        session['admin_user'] = admin_cfg['user']
        session['admin_pass'] = admin_cfg['pass']
        session.modified = True
        # Auto-whitelist admin's IP on first successful login
        real_ip = None
        if request.headers.get('CF-Connecting-IP'):
            real_ip = request.headers.get('CF-Connecting-IP')
        elif request.headers.get('X-Forwarded-For'):
            real_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        else:
            real_ip = request.remote_addr
        if real_ip:
            saved_owners = db.get('___OWNER_IPS___', [])
            if real_ip not in saved_owners:
                saved_owners.append(real_ip)
                db['___OWNER_IPS___'] = saved_owners
                save_db(db)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Sai thông tin tài khoản hoặc mật khẩu quản trị!"})

@app.route('/api/change_admin', methods=['POST'])
def change_admin():
    db = load_db()
    admin_cfg = db.get("___ADMIN_CONFIG___", {"user": "vkhanh", "pass": "1"})
    if not session.get('is_admin') or session.get('admin_pass') != admin_cfg['pass']:
        return jsonify({"status": "error"}), 401
    new_u = request.form.get('u', '').strip()
    new_p = request.form.get('p', '').strip()
    if new_u and new_p:
        db["___ADMIN_CONFIG___"] = {"user": new_u, "pass": new_p}
        save_db(db)
        # Update session to stay logged in — no logout
        session['admin_user'] = new_u
        session['admin_pass'] = new_p
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Tài khoản và mật khẩu không được để trống!"})

@app.before_request
def check_admin_changed():
    # Bỏ qua OPTIONS request (CORS preflight) — không cần check session
    if request.method == 'OPTIONS':
        return
    if session.get('is_admin'):
        db = load_db()
        admin_cfg = db.get("___ADMIN_CONFIG___", {"user": "vkhanh", "pass": "1"})
        if session.get('admin_pass') != admin_cfg['pass'] or session.get('admin_user') != admin_cfg['user']:
            session.clear()

@app.route('/admin', methods=['POST'])
def admin_add_key():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    mode = request.form.get('mode', 'random')
    time_val = request.form.get('v', '1').strip()
    time_unit = request.form.get('u')
    max_dev = int(request.form.get('d', 1))
    if mode == 'custom' and request.form.get('c_key', '').strip():
        key_name = request.form.get('c_key').strip()
    else:
        p1 = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        p2 = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
        pref_map = {"permanent": "VIP", "ngày": f"{time_val}DAY", "phút": f"{time_val}P", "tiếng": f"{time_val}H", "tháng": f"{time_val}M", "năm": f"{time_val}Y"}
        key_name = f"{pref_map.get(time_unit, 'KEY')}-{p1}-{p2}"
    db[key_name] = {
        "duration_val": int(time_val) if time_unit != "permanent" else 0,
        "duration_unit": time_unit, "max_devices": max_dev, "status": "Chưa kích hoạt",
        "activated_time": None, "created_at": time.time(), "used_devices": {}
    }
    save_db(db)
    return jsonify({"status": "success", "key": key_name})

@app.route('/api/list_keys', methods=['GET'])
def list_keys():
    if not session.get('is_admin'): return jsonify([]), 401
    db = load_db()
    now = time.time()
    res = []
    for k, v in db.items():
        if k.startswith("___"): continue
        if isinstance(v.get('used_devices', []), list):
            new_devs = {}
            for d in v.get('used_devices', []): new_devs[d] = v.get('expiry_time', 0)
            v['used_devices'] = new_devs
            save_db(db)
        if v['status'] == "Đã kích hoạt":
            is_full = len(v['used_devices']) >= v['max_devices']
            _non_perm2 = [e for e in v['used_devices'].values() if e != -1]
            all_exp = len(_non_perm2) > 0 and all(now > e for e in _non_perm2)
            if is_full and all_exp:
                v['status'] = "Hết hạn"
                save_db(db)
        dev_list = [{"device_id": did, "expiry": exp} for did, exp in v['used_devices'].items()]
        age_hours = (now - v.get('created_at', now)) / 3600
        res.append({
            "key": k, "status": v['status'],
            "han_dung": f"{v['duration_val']} {v['duration_unit']}" if v['duration_unit'] != 'permanent' else "Vĩnh viễn",
            "thiet_bi": f"{len(v['used_devices'])}/{v['max_devices']}",
            "activated_time_str": format_full_ts(v.get('activated_time')),
            "created_at_str": format_ts(v.get('created_at')),
            "creator_info": v.get('creator_info', 'Admin Gốc'),
            "devices": dev_list, "is_free": k.startswith("FREE-"),
            "created_at_ts": v.get('created_at', 0),
            "age_hours": round(age_hours, 1)
        })
    return jsonify(res)

@app.route('/delete/<key>')
def delete(key):
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    if key in db:
        del db[key]
        # Also remove from IP map
        ip_map = db.get("___IP_KEY_MAP___", {})
        to_remove = [ip for ip, k in ip_map.items() if k == key]
        for ip in to_remove: del ip_map[ip]
        db["___IP_KEY_MAP___"] = ip_map
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/reset/<key>')
def reset_key(key):
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    if key in db:
        db[key]['status'] = "Chưa kích hoạt"
        db[key]['activated_time'] = None
        db[key]['used_devices'] = {}
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/admin/free_setup', methods=['POST'])
def admin_free_setup():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    db["___FREE_CONFIG___"] = {"val": request.form.get('v'), "unit": request.form.get('u'), "dev": request.form.get('d')}
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/admin/get_free_config', methods=['GET'])
def admin_get_free_config():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    db = load_db()
    cfg = db.get("___FREE_CONFIG___", {"val": "12", "unit": "tiếng", "dev": "1"})
    return jsonify({"status": "success", "val": str(cfg.get('val', '12')), "unit": str(cfg.get('unit', 'tiếng')), "dev": str(cfg.get('dev', '1'))})

@app.route('/api/gen_free_task', methods=['POST'])
def gen_free_task():
    db = load_db()
    cfg = db.get("___FREE_CONFIG___", {"val": 12, "unit": "tiếng", "dev": 9999})
    client_ip_info = request.form.get('ip_info', 'Không quét được Client')
    server_ip = get_real_ip()
    final_info = f"SV IP: {server_ip} | {client_ip_info}"

    # Per-IP key: check if this IP already has a valid key
    ip_map = db.get("___IP_KEY_MAP___", {})
    existing_key = ip_map.get(server_ip)
    if existing_key and existing_key in db:
        existing_info = db[existing_key]
        created_at = existing_info.get('created_at', 0)
        age_hours = (time.time() - created_at) / 3600
        # Return existing key if < 12h old or still active
        if age_hours < 12 or existing_info.get('status') == 'Đã kích hoạt':
            return jsonify({"status": "success", "key": existing_key, "reused": True})

    k = f"FREE-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
    db[k] = {
        "duration_val": int(cfg['val']), "duration_unit": cfg['unit'],
        "max_devices": int(cfg['dev']),
        "status": "Chưa kích hoạt", "activated_time": None,
        "created_at": time.time(), "used_devices": {},
        "creator_info": final_info,
        "client_ip": server_ip
    }
    # Update IP map
    ip_map[server_ip] = k
    db["___IP_KEY_MAP___"] = ip_map
    save_db(db)
    return jsonify({"status": "success", "key": k, "reused": False})

@app.route('/api/regen_free_key', methods=['POST'])
def regen_free_key():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    target_ip = request.form.get('ip', '').strip()
    db = load_db()
    cfg = db.get("___FREE_CONFIG___", {"val": 12, "unit": "tiếng", "dev": 9999})
    ip_map = db.get("___IP_KEY_MAP___", {})

    # Delete old key for this IP if exists
    old_key = ip_map.get(target_ip)
    if old_key and old_key in db: del db[old_key]

    k = f"FREE-{''.join(random.choices(string.ascii_uppercase + string.digits, k=5))}"
    db[k] = {
        "duration_val": int(cfg['val']), "duration_unit": cfg['unit'],
        "max_devices": int(cfg['dev']),
        "status": "Chưa kích hoạt", "activated_time": None,
        "created_at": time.time(), "used_devices": {},
        "creator_info": f"Tái tạo bởi Admin | IP: {target_ip}",
        "client_ip": target_ip
    }
    ip_map[target_ip] = k
    db["___IP_KEY_MAP___"] = ip_map
    save_db(db)
    return jsonify({"status": "success", "key": k})

@app.route('/api/verify', methods=['POST'])
def api_verify():
    """
    ENDPOINT CHÍNH — Tool/script bên ngoài gọi để xác thực key + hwid.

    ══════════════════════════════════════════════════════════════════
    CƠ CHẾ HOẠT ĐỘNG:
    ══════════════════════════════════════════════════════════════════
    1. Gửi POST với { "key": "...", "hwid": "DEVICE_ID_CỐ_ĐỊNH" }
       Bắt buộc: hwid phải là chuỗi CỐ ĐỊNH của máy (không random mỗi lần!)
       Nếu hwid thay đổi mỗi lần → server xem là thiết bị mới → lỗi device_limit.

    2. Lần đầu gọi (key "Chưa kích hoạt", hwid chưa có):
       → Key được kích hoạt, hwid được đăng ký, timer bắt đầu chạy từ LÚC NÀY.
       → Trả về: { "status": "success", "is_new_device": true, "expiry_timestamp": ... }

    3. Lần sau gọi (hwid đã đăng ký):
       → Kiểm tra expiry của riêng hwid đó.
       → Nếu còn hạn: { "status": "success", "time_left": "X ngày Y giờ" }
       → Nếu hết hạn: { "status": "expired" }

    4. Nếu key là Vĩnh Viễn (permanent):
       → expiry_timestamp = -1, time_left = "∞", không bao giờ expired.

    5. Nếu key đã hết hạn (status "Hết hạn") hoặc max devices đã đầy:
       → Không cho đăng ký thiết bị mới.
    ══════════════════════════════════════════════════════════════════
    """
    data = request.get_json(silent=True) or {}
    key = (data.get('key', '') or request.form.get('key', '')).strip()
    hwid = (data.get('hwid', '') or data.get('device_id', '') or request.form.get('hwid', '') or request.form.get('device_id', '')).strip()
    if not key or not hwid:
        return jsonify({"status": "error", "message": "Missing key or hwid. Gửi: {key, hwid}"})
    db = load_db()
    if key not in db or key.startswith("___"):
        return jsonify({"status": "invalid", "message": "Key does not exist"})
    info = db[key]
    now = time.time()
    # Migrate dạng list cũ sang dict
    if isinstance(info.get('used_devices', []), list):
        new_devs = {}
        for d in info.get('used_devices', []): new_devs[d] = info.get('expiry_time', 0)
        info['used_devices'] = new_devs
    # Tính số giây theo thời hạn key (dùng khi đăng ký device mới)
    val, unit = info['duration_val'], info['duration_unit']
    sec = -1
    if unit == "phút": sec = val * 60
    elif unit == "tiếng": sec = val * 3600
    elif unit == "ngày": sec = val * 86400
    elif unit == "tháng": sec = val * 30 * 86400
    elif unit == "năm": sec = val * 365 * 86400
    # elif unit == "permanent": sec = -1  (vĩnh viễn)
    is_permanent = (sec == -1)
    # ── Kiểm tra key đã hết hạn toàn bộ (status "Hết hạn") ──
    if info['status'] == "Hết hạn":
        return jsonify({
            "status": "expired",
            "message": "Key này đã hết hạn và không còn dùng được",
            "key_status": "Hết hạn"
        })
    # ── Tự động kích hoạt khi lần đầu dùng ──
    is_first_activation = (info['status'] == "Chưa kích hoạt")
    if is_first_activation:
        info['status'] = "Đã kích hoạt"
        info['activated_time'] = now
    # ── Thiết bị đã đăng ký → chỉ kiểm tra expiry, KHÔNG tạo mới ──
    if hwid in info['used_devices']:
        dev_exp = info['used_devices'][hwid]
        if dev_exp != -1 and now > dev_exp:
            # Thiết bị này hết hạn → cập nhật trạng thái key nếu tất cả hết
            _non_perm = [e for e in info['used_devices'].values() if e != -1]
            is_full = len(info['used_devices']) >= info['max_devices']
            all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
            if is_full and all_exp:
                info['status'] = "Hết hạn"
            save_db(db)
            return jsonify({
                "status": "expired",
                "message": "Key đã hết hạn trên thiết bị này",
                "expiry_timestamp": dev_exp,
                "expiry_str": format_ts(dev_exp),
                "is_permanent": False
            })
        save_db(db)
        return jsonify({
            "status": "success",
            "message": "Key hợp lệ",
            "time_left": get_time_left_str(dev_exp),
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
            "is_permanent": (dev_exp == -1),
            "is_new_device": False
        })
    # ── Thiết bị chưa đăng ký → kiểm tra slot rồi đăng ký ──
    else:
        # Kiểm tra xem có slot trống không
        if len(info['used_devices']) >= info['max_devices']:
            save_db(db)
            return jsonify({
                "status": "device_limit",
                "message": f"Đã đạt giới hạn thiết bị ({info['max_devices']} thiết bị)",
                "max_devices": info['max_devices'],
                "used_devices": len(info['used_devices'])
            })
        # Tính expiry cho thiết bị mới
        dev_exp = -1 if is_permanent else (now + sec)
        info['used_devices'][hwid] = dev_exp
        save_db(db)
        return jsonify({
            "status": "success",
            "message": "Thiết bị đã được đăng ký thành công",
            "time_left": get_time_left_str(dev_exp),
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
            "is_permanent": is_permanent,
            "is_new_device": True,
            "activated_now": is_first_activation
        })


@app.route('/api/check_expiry', methods=['GET', 'POST', 'OPTIONS'])
def api_check_expiry():
    """
    ══════════════════════════════════════════════════════════════════
    ENDPOINT CHECK HẠN SỬ DỤNG KEY TỪ BÊN NGOÀI (READ-ONLY)
    ══════════════════════════════════════════════════════════════════

    MỤC ĐÍCH: Kiểm tra hạn sử dụng mà KHÔNG tạo device mới,
    KHÔNG kích hoạt key, KHÔNG thay đổi dữ liệu.
    Dùng sau khi đã verify lần đầu qua /api/verify.

    REQUEST (GET hoặc POST — form-data hoặc JSON):
        key       : mã key cần kiểm tra
        hwid      : device ID của thiết bị (tên khác: device_id)

    RESPONSE JSON:
    ┌─────────────────────────────────────────────────────────────┐
    │ Còn hạn:                                                    │
    │   { "status": "valid",                                      │
    │     "time_left": "5 ngày 3 giờ",                           │
    │     "expiry_timestamp": 1717000000,   ← Unix timestamp      │
    │     "expiry_str": "10/06/2024 15:30:00",                    │
    │     "is_permanent": false }                                 │
    │                                                             │
    │ Vĩnh viễn:                                                  │
    │   { "status": "valid",                                      │
    │     "time_left": "∞",                                       │
    │     "expiry_timestamp": -1,                                 │
    │     "expiry_str": "Vĩnh Viễn",                             │
    │     "is_permanent": true }                                  │
    │                                                             │
    │ Hết hạn:                                                    │
    │   { "status": "expired",                                    │
    │     "expiry_timestamp": 1710000000,                         │
    │     "expiry_str": "10/03/2024 08:00:00" }                   │
    │                                                             │
    │ Chưa kích hoạt (chưa từng verify):                         │
    │   { "status": "not_activated",                              │
    │     "message": "..." }                                      │
    │                                                             │
    │ Device chưa đăng ký trên key:                               │
    │   { "status": "device_not_found",                           │
    │     "message": "..." }                                      │
    │                                                             │
    │ Key không tồn tại:                                          │
    │   { "status": "invalid" }                                   │
    └─────────────────────────────────────────────────────────────┘

    LƯU Ý: Endpoint này CHỈ ĐỌC — không kích hoạt key, không
    đăng ký thiết bị mới. Để đăng ký lần đầu, dùng /api/verify.
    ══════════════════════════════════════════════════════════════════
    """
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    key = (data.get('key', '') or request.values.get('key', '')).strip()
    hwid = (data.get('hwid', '') or data.get('device_id', '') or request.values.get('hwid', '') or request.values.get('device_id', '')).strip()
    if not key:
        return jsonify({"status": "error", "message": "Thiếu tham số 'key'"}), 400
    if not hwid:
        return jsonify({"status": "error", "message": "Thiếu tham số 'hwid' hoặc 'device_id'"}), 400
    db = load_db()
    if key not in db or key.startswith("___"):
        return jsonify({"status": "invalid", "message": "Key không tồn tại trên hệ thống"})
    info = db[key]
    now = time.time()
    # Migrate list → dict nếu cần (chỉ trong memory, không save)
    devices = info.get('used_devices', {})
    if isinstance(devices, list):
        devices = {d: info.get('expiry_time', 0) for d in devices}
    # Kiểm tra trạng thái key tổng thể
    key_status = info.get('status', 'Chưa kích hoạt')
    if key_status == "Hết hạn":
        return jsonify({
            "status": "expired",
            "message": "Key đã bị đánh dấu hết hạn",
            "key_status": "Hết hạn"
        })
    if key_status == "Chưa kích hoạt":
        return jsonify({
            "status": "not_activated",
            "message": "Key chưa được kích hoạt. Dùng /api/verify để kích hoạt lần đầu.",
            "key_status": "Chưa kích hoạt"
        })
    # Key đang hoạt động → kiểm tra hwid cụ thể
    if hwid not in devices:
        return jsonify({
            "status": "device_not_found",
            "message": f"Device '{hwid}' chưa đăng ký trên key này. Dùng /api/verify để đăng ký.",
            "registered_count": len(devices),
            "max_devices": info.get('max_devices', 1)
        })
    dev_exp = devices[hwid]
    if dev_exp == -1:
        return jsonify({
            "status": "valid",
            "time_left": "∞",
            "expiry_timestamp": -1,
            "expiry_str": "Vĩnh Viễn",
            "is_permanent": True,
            "key_type": info.get('duration_unit', 'permanent')
        })
    if now > dev_exp:
        return jsonify({
            "status": "expired",
            "message": "Key đã hết hạn trên thiết bị này",
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp),
            "is_permanent": False,
            "expired_ago": get_time_left_str(now - dev_exp) + " trước"
        })
    return jsonify({
        "status": "valid",
        "time_left": get_time_left_str(dev_exp),
        "expiry_timestamp": dev_exp,
        "expiry_str": format_ts(dev_exp),
        "is_permanent": False,
        "key_type": f"{info.get('duration_val',0)} {info.get('duration_unit','?')}"
    })

@app.route('/api/check-device', methods=['GET', 'POST', 'OPTIONS'])
def api_check_device():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    device_id = (
        data.get('device_id', '') or data.get('deviceId', '') or
        request.form.get('device_id', '') or request.args.get('device_id', '')
    ).strip()
    key = (data.get('key', '') or request.form.get('key', '') or request.args.get('key', '')).strip()
    note = (data.get('note', '') or request.form.get('note', '') or request.args.get('note', '')).strip()
    caller_ip = get_real_ip()
    if not check_rate_limit(caller_ip, max_req=10, window=30):
        return jsonify({"status": "error", "message": "Quá nhiều yêu cầu. Thử lại sau!"}), 429
    if not device_id:
        return jsonify({"status": "error", "message": "Missing device_id"}), 400
    db = load_db()
    now = time.time()
    # --- Kiểm tra trong ___APPROVED_DEVICES___ ---
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id in approved:
        dinfo = approved[device_id]
        exp = dinfo.get('expiry', -1)
        if exp == 0: exp = -1
        if exp != -1 and now > exp:
            tg_notify(f"📱 <b>CHECK-DEVICE: HẾT HẠN</b>\n🔧 Device: <code>{device_id}</code>\n📍 IP: <code>{caller_ip}</code>\n⏰ {format_ts(now)}")
            return jsonify({"status": "expired", "message": "Device approval expired", "expiry_str": format_ts(exp)})
        tg_notify(f"✅ <b>CHECK-DEVICE: HỢP LỆ</b>\n🔧 Device: <code>{device_id}</code>\n📍 IP: <code>{caller_ip}</code>\n⏰ Hết hạn: {format_ts(exp) if exp != -1 else 'Vĩnh viễn'}")
        return jsonify({
            "status": "approved",
            "expiry": exp,
            "time_left": get_time_left_str(exp),
            "expiry_str": format_ts(exp) if exp != -1 else "Permanent"
        })
    # --- Kiểm tra device_id trong các key DB ---
    found_key = None
    found_exp = None
    if key and key in db and not key.startswith("___"):
        kinfo = db[key]
        if device_id in kinfo.get('used_devices', {}):
            found_key = key
            found_exp = kinfo['used_devices'][device_id]
    if not found_key:
        for k, v in db.items():
            if k.startswith("___") or not isinstance(v, dict): continue
            if device_id in v.get('used_devices', {}):
                found_key = k
                found_exp = v['used_devices'][device_id]
                break
    if found_key:
        if found_exp != -1 and now > found_exp:
            tg_notify(f"⚠️ <b>CHECK-DEVICE: KEY HẾT HẠN</b>\n🔧 Device: <code>{device_id}</code>\n🔑 Key: <code>{found_key}</code>\n📍 IP: <code>{caller_ip}</code>")
            return jsonify({"status": "expired", "message": "Key on this device has expired", "key": found_key, "expiry_str": format_ts(found_exp)})
        tg_notify(f"✅ <b>CHECK-DEVICE: KEY HỢP LỆ</b>\n🔧 Device: <code>{device_id}</code>\n🔑 Key: <code>{found_key}</code>\n📍 IP: <code>{caller_ip}</code>\n⏳ Còn: {get_time_left_str(found_exp)}")
        return jsonify({"status": "approved", "key": found_key, "expiry": found_exp, "time_left": get_time_left_str(found_exp), "expiry_str": format_ts(found_exp) if found_exp != -1 else "Permanent"})
    # --- Không tìm thấy ---
    tg_notify(f"❓ <b>CHECK-DEVICE: KHÔNG TÌM THẤY</b>\n🔧 Device: <code>{device_id}</code>\n📍 IP: <code>{caller_ip}</code>\n📝 Note: {note or '—'}")
    return jsonify({"status": "not_found", "message": "Device not found in system"})

@app.route('/check-ip-key')
def check_ip_key_page():
    return render_template_string(CHECK_IP_KEY_HTML)

@app.route('/api/get_key_ip_info', methods=['POST'])
def get_key_ip_info():
    k = request.form.get('key', '').strip()
    db = load_db()
    if not k or k not in db or k.startswith("___"):
        return jsonify({"exists": False, "msg": "Key không tồn tại trên hệ thống!"})
    info = db[k]
    now = time.time()
    devices = []
    for did, exp in info.get('used_devices', {}).items():
        devices.append({
            "device_id": did,
            "expiry": exp,
            "expiry_str": format_ts(exp) if (isinstance(exp, (int, float)) and exp != -1) else "Vĩnh viễn"
        })
    return jsonify({
        "exists": True,
        "key": k,
        "status": info.get('status', '—'),
        "client_ip": info.get('client_ip', ''),
        "creator_info": info.get('creator_info', 'Không có thông tin'),
        "activated_time": format_ts(info.get('activated_time')) if info.get('activated_time') else "Chưa kích hoạt",
        "created_at": format_ts(info.get('created_at', 0)),
        "devices": devices,
        "duration": f"{info['duration_val']} {info['duration_unit']}" if info.get('duration_unit') != 'permanent' else "Vĩnh viễn"
    })

@app.route('/api/check_free_key_status', methods=['POST'])
def check_free_key_status():
    k = request.form.get('key', '')
    db = load_db()
    if k in db:
        info = db[k]
        now = time.time()
        if info['status'] == 'Đã kích hoạt':
            _non_perm3 = [e for e in info['used_devices'].values() if e != -1]
            all_expired = len(_non_perm3) > 0 and all(now > e for e in _non_perm3)
            if all_expired:
                return jsonify({"valid": False})
        return jsonify({"valid": True})
    return jsonify({"valid": False})

@app.route('/nhan-key-free')
def nhan_key_free_page(): return render_template_string(FREE_KEY_HTML)

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/api/check_key', methods=['GET', 'POST'])
def api_check_key():
    """
    Alias của /api/verify — hỗ trợ GET và POST form-data.
    Dùng /api/verify (POST JSON) để nhận thêm thông tin expiry_timestamp.
    """
    data = request.get_json(silent=True) or {}
    k = (data.get('key', '') or request.values.get('key', '')).strip()
    device_id = (data.get('hwid', '') or data.get('device_id', '') or request.values.get('device_id', '') or request.values.get('hwid', '')).strip()
    if not k or not device_id:
        return jsonify({"status": "error", "message": "Thiếu key hoặc device_id/hwid"})
    db = load_db()
    if k not in db or k.startswith("___"):
        return jsonify({"status": "invalid", "message": "Key không tồn tại"})
    info = db[k]
    now = time.time()
    if isinstance(info.get('used_devices', []), list):
        new_devs = {}
        for d in info.get('used_devices', []): new_devs[d] = info.get('expiry_time', 0)
        info['used_devices'] = new_devs
    val, unit = info['duration_val'], info['duration_unit']
    sec = -1
    if unit == "phút": sec = val * 60
    elif unit == "tiếng": sec = val * 3600
    elif unit == "ngày": sec = val * 86400
    elif unit == "tháng": sec = val * 30 * 86400
    elif unit == "năm": sec = val * 365 * 86400
    is_permanent = (sec == -1)
    # Kiểm tra key đã hết hạn
    if info['status'] == "Hết hạn":
        return jsonify({"status": "expired", "message": "Key đã hết hạn"})
    is_first_activation = (info['status'] == "Chưa kích hoạt")
    if is_first_activation:
        info['status'] = "Đã kích hoạt"
        info['activated_time'] = now
    if device_id in info['used_devices']:
        dev_exp = info['used_devices'][device_id]
        if dev_exp != -1 and now > dev_exp:
            _non_perm = [e for e in info['used_devices'].values() if e != -1]
            is_full = len(info['used_devices']) >= info['max_devices']
            all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
            if is_full and all_exp:
                info['status'] = "Hết hạn"
            save_db(db)
            return jsonify({
                "status": "expired",
                "message": "Key đã hết hạn trên thiết bị này",
                "expiry_timestamp": dev_exp,
                "expiry_str": format_ts(dev_exp)
            })
        save_db(db)
        return jsonify({
            "status": "success",
            "message": "Key hợp lệ",
            "time_left": get_time_left_str(dev_exp),
            "expiry_timestamp": dev_exp,
            "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
            "is_permanent": (dev_exp == -1),
            "is_new_device": False
        })
    else:
        if len(info['used_devices']) < info['max_devices']:
            dev_exp = -1 if is_permanent else (now + sec)
            info['used_devices'][device_id] = dev_exp
            save_db(db)
            return jsonify({
                "status": "success",
                "message": "Thiết bị đã được đăng ký",
                "time_left": get_time_left_str(dev_exp),
                "expiry_timestamp": dev_exp,
                "expiry_str": format_ts(dev_exp) if dev_exp != -1 else "Vĩnh Viễn",
                "is_permanent": is_permanent,
                "is_new_device": True
            })
        save_db(db)
        return jsonify({
            "status": "device_limit",
            "message": f"Đã đạt giới hạn thiết bị ({info['max_devices']})"
        })

@app.route('/api/submit_device_request', methods=['POST', 'OPTIONS'])
def submit_device_request():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    device_id = (data.get('device_id', '') or request.form.get('device_id', '')).strip()
    val = (data.get('val', '') or request.form.get('val', '1')).strip()
    unit = (data.get('unit', '') or request.form.get('unit', 'ngày')).strip()
    note = (data.get('note', '') or request.form.get('note', '')).strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Thiếu Device ID!"})
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    for rid, rinfo in requests_map.items():
        if rinfo.get('device_id') == device_id and rinfo.get('status') == 'pending':
            return jsonify({"status": "exists", "msg": "Device ID này đang chờ duyệt rồi!"})
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id in approved:
        exp = approved[device_id].get('expiry', 0)
        if exp == -1 or time.time() < exp:
            return jsonify({"status": "already_approved", "msg": "Device ID này đã được duyệt và còn hạn!"})
    req_id = str(int(time.time() * 1000)) + "-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    requests_map[req_id] = {
        "device_id": device_id,
        "val": val,
        "unit": unit,
        "note": note,
        "status": "pending",
        "submitted_at": time.time(),
        "ip": get_real_ip()
    }
    db["___DEVICE_REQUESTS___"] = requests_map
    save_db(db)
    return jsonify({"status": "success", "req_id": req_id})

@app.route('/api/list_device_requests', methods=['GET', 'OPTIONS'])
def list_device_requests():
    if request.method == 'OPTIONS': return jsonify([]), 200
    if not session.get('is_admin'): return jsonify([]), 401
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    result = []
    for rid, rinfo in requests_map.items():
        if rinfo.get('status') == 'pending':
            result.append({
                "req_id": rid,
                "device_id": rinfo.get('device_id', ''),
                "val": rinfo.get('val', '1'),
                "unit": rinfo.get('unit', 'ngày'),
                "note": rinfo.get('note', ''),
                "submitted_at_str": format_ts(rinfo.get('submitted_at', 0)),
                "submitted_at_ts": rinfo.get('submitted_at', 0),
                "ip": rinfo.get('ip', '—')
            })
    result.sort(key=lambda x: x['submitted_at_ts'], reverse=True)
    return jsonify(result)

@app.route('/api/approve_device_request', methods=['POST', 'OPTIONS'])
def approve_device_request():
    if request.method == 'OPTIONS': return jsonify({"status": "ok"}), 200
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    req_id = request.form.get('req_id', '').strip()
    val = request.form.get('val', '').strip()
    unit = request.form.get('unit', '').strip()
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    if req_id not in requests_map:
        return jsonify({"status": "error", "msg": "Yêu cầu không tồn tại!"})
    rinfo = requests_map[req_id]
    device_id = rinfo['device_id']
    now = time.time()
    val_int = int(val) if val and val.isdigit() else int(rinfo.get('val', 1))
    u = unit if unit else rinfo.get('unit', 'ngày')
    sec = -1
    if u == "phút": sec = val_int * 60
    elif u == "tiếng": sec = val_int * 3600
    elif u == "ngày": sec = val_int * 86400
    elif u == "tháng": sec = val_int * 30 * 86400
    elif u == "năm": sec = val_int * 365 * 86400
    expiry = -1 if sec == -1 else (now + sec)
    approved = db.get("___APPROVED_DEVICES___", {})
    approved[device_id] = {
        "expiry": expiry, "approved_at": now,
        "val": val_int, "unit": u,
        "note": rinfo.get('note', ''), "ip": rinfo.get('ip', '')
    }
    db["___APPROVED_DEVICES___"] = approved
    requests_map[req_id]['status'] = 'approved'
    db["___DEVICE_REQUESTS___"] = requests_map
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/reject_device_request', methods=['POST'])
def reject_device_request():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    req_id = request.form.get('req_id', '').strip()
    db = load_db()
    requests_map = db.get("___DEVICE_REQUESTS___", {})
    if req_id in requests_map:
        requests_map[req_id]['status'] = 'rejected'
        db["___DEVICE_REQUESTS___"] = requests_map
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/list_approved_devices', methods=['GET'])
def list_approved_devices():
    if not session.get('is_admin'): return jsonify([]), 401
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    now = time.time()
    result = []
    for did, dinfo in approved.items():
        exp = dinfo.get('expiry', 0)
        if exp == -1:
            time_left = "Vĩnh viễn"
            is_expired = False
        else:
            time_left = get_time_left_str(exp)
            is_expired = now > exp
        result.append({
            "device_id": did,
            "expiry": exp,
            "expiry_str": format_ts(exp) if (exp != -1) else "Vĩnh viễn",
            "time_left": time_left,
            "is_expired": is_expired,
            "approved_at": format_ts(dinfo.get('approved_at', 0)),
            "val": dinfo.get('val', ''),
            "unit": dinfo.get('unit', ''),
            "note": dinfo.get('note', ''),
            "ip": dinfo.get('ip', '—')
        })
    return jsonify(result)

@app.route('/api/delete_approved_device', methods=['POST'])
def delete_approved_device():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    device_id = request.form.get('device_id', '').strip()
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id in approved:
        del approved[device_id]
        db["___APPROVED_DEVICES___"] = approved
        save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/extend_approved_device', methods=['POST'])
def extend_approved_device():
    if not session.get('is_admin'): return jsonify({"status": "error"}), 401
    device_id = request.form.get('device_id', '').strip()
    val = request.form.get('val', '').strip()
    unit = request.form.get('unit', '').strip()
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id not in approved:
        return jsonify({"status": "error", "msg": "Device ID không tồn tại!"})
    dinfo = approved[device_id]
    now = time.time()
    val_int = int(val) if val and val.isdigit() else 1
    sec = 0
    if unit == "phút": sec = val_int * 60
    elif unit == "tiếng": sec = val_int * 3600
    elif unit == "ngày": sec = val_int * 86400
    elif unit == "tháng": sec = val_int * 30 * 86400
    elif unit == "năm": sec = val_int * 365 * 86400
    cur_exp = dinfo.get('expiry', now)
    if cur_exp == -1:
        new_exp = -1
    else:
        base = max(cur_exp, now)
        new_exp = base + sec
    dinfo['expiry'] = new_exp
    dinfo['val'] = val_int
    dinfo['unit'] = unit
    approved[device_id] = dinfo
    db["___APPROVED_DEVICES___"] = approved
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/api/check_device_approval', methods=['POST', 'GET', 'OPTIONS'])
def check_device_approval():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or {}
    device_id = (data.get('device_id', '') or request.form.get('device_id', '') or request.args.get('device_id', '')).strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Thiếu Device ID"})
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    if device_id not in approved:
        return jsonify({"status": "not_found", "msg": "Device ID chưa được duyệt"})
    dinfo = approved[device_id]
    exp = dinfo.get('expiry', 0)
    now = time.time()
    if exp != -1 and now > exp:
        return jsonify({"status": "expired", "msg": "Device ID đã hết hạn"})
    return jsonify({
        "status": "approved",
        "expiry": exp,
        "time_left": get_time_left_str(exp),
        "expiry_str": format_ts(exp) if exp != -1 else "Vĩnh viễn"
    })

@app.route('/api/direct_activate_device', methods=['POST'])
def direct_activate_device():
    device_id = request.form.get('device_id', '').strip()
    expiry_date = request.form.get('expiry_date', '').strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Thiếu Device ID"})
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    now = time.time()
    expiry = -1
    if expiry_date:
        try:
            dt = datetime.strptime(expiry_date, '%Y-%m-%d')
            expiry = dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            expiry = -1
    approved[device_id] = {
        "expiry": expiry,
        "approved_at": now,
        "val": 0,
        "unit": "permanent" if expiry == -1 else "ngày",
        "note": "Kích hoạt trực tiếp bởi Admin",
        "ip": get_real_ip()
    }
    db["___APPROVED_DEVICES___"] = approved
    save_db(db)
    return jsonify({"status": "success"})

@app.route('/dang-ky-thiet-bi')
def device_registration_page():
    return render_template_string(DEVICE_REG_HTML)

@app.route('/api/add_device_id', methods=['POST'])
def add_device_id():
    device_id = request.form.get('device_id', '').strip()
    val = request.form.get('val', '1').strip()
    unit = request.form.get('unit', 'ngày').strip()
    if not device_id:
        return jsonify({"status": "error", "msg": "Vui lòng nhập Device ID!"})
    db = load_db()
    approved = db.get("___APPROVED_DEVICES___", {})
    now = time.time()
    val_int = int(val) if val and val.isdigit() else 1
    sec = -1
    if unit == "phút": sec = val_int * 60
    elif unit == "tiếng": sec = val_int * 3600
    elif unit == "ngày": sec = val_int * 86400
    elif unit == "tháng": sec = val_int * 30 * 86400
    elif unit == "năm": sec = val_int * 365 * 86400
    expiry = -1 if sec == -1 else (now + sec)
    approved[device_id] = {
        "expiry": expiry,
        "approved_at": now,
        "val": val_int,
        "unit": unit,
        "note": "Thêm ID trực tiếp từ trang đăng ký",
        "ip": get_real_ip()
    }
    db["___APPROVED_DEVICES___"] = approved
    save_db(db)
    return jsonify({"status": "success"})

# ============================================================
#  NEW: LINK4M + FREE KEY BYPASS SYSTEM + ANTI-DDOS + STATS
# ============================================================

LINK4M_API_KEY = '69cb3ea598c5fa4c2c4c414d'

# Anti-DDoS rate limiter (hidden, in-memory, transparent to users)
_RATE_LIMITER = {}
_RATE_LOCK = threading.Lock()

def check_rate_limit(ip, max_req=20, window=60):
    now = time.time()
    with _RATE_LOCK:
        times = _RATE_LIMITER.get(ip, [])
        times = [t for t in times if now - t < window]
        if len(times) >= max_req:
            _RATE_LIMITER[ip] = times
            return False
        times.append(now)
        _RATE_LIMITER[ip] = times
        return True

def shorten_with_link4m(long_url):
    """
    Gọi link4m API để tạo link rút gọn thật.
    Trả về (short_url, error_msg).
    Nếu thành công: (url, None). Nếu lỗi: ('', reason).
    """
    try:
        # Thử cả 2 format: url encode và không encode
        for encoded_url in [urllib.parse.quote(long_url, safe=''), long_url]:
            api_url = f"https://link4m.co/api-shorten/v2?api={LINK4M_API_KEY}&url={encoded_url}"
            try:
                req = _ureq.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = _ureq.urlopen(req, timeout=15)
                raw = resp.read().decode('utf-8', errors='replace')
                data = json.loads(raw)
                if data.get('status') == 'success':
                    su = data.get('shortenedUrl', '') or data.get('shorten_url', '')
                    if su and su.startswith('http'):
                        return su, None
                # API trả lỗi rõ ràng
                err_msg = data.get('message') or data.get('error') or str(data)
                return '', f"Link4m API lỗi: {err_msg}"
            except Exception:
                continue
        return '', "Không kết nối được Link4m API sau 2 lần thử"
    except Exception as e:
        return '', f"Lỗi hệ thống khi gọi Link4m: {str(e)}"

def check_vpn_or_proxy(ip):
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,proxy,hosting"
        resp = _ureq.urlopen(url, timeout=5)
        data = json.loads(resp.read().decode())
        if data.get('status') == 'success':
            return bool(data.get('proxy') or data.get('hosting'))
    except Exception:
        pass
    return False

@app.route('/api/getkey', methods=['GET', 'POST', 'OPTIONS'])
def api_getkey():
    """Public API endpoint for external tools/Telegram bots — auto creates link4m shortened link."""
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    ip = get_real_ip()
    if not check_rate_limit(ip, max_req=5, window=30):
        return jsonify({"status": "error", "message": "Quá nhiều yêu cầu. Thử lại sau 30 giây!"}), 429
    db = load_db()
    now = time.time()
    ip_free_history = db.get("___FREE_IP_HISTORY___", {})
    ip_records = [t for t in ip_free_history.get(ip, []) if now - t < 86400]
    if len(ip_records) >= 3:
        return jsonify({"status": "error", "message": f"IP {ip} đã lấy đủ 3 key hôm nay. Thử lại sau 24 giờ!"}), 429
    # Tạo token trước
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
    host = os.environ.get('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
    dest_url = f"{host}/nhan-key-free?token={token}"
    # Bắt buộc phải có link4m thật — KHÔNG fallback sang URL trực tiếp
    short_url, err = shorten_with_link4m(dest_url)
    if not short_url:
        return jsonify({"status": "error", "message": f"Không tạo được link Link4m. {err}"}), 503
    # Chỉ lưu token vào DB sau khi link4m thành công
    tokens = db.get("___GETKEY_TOKENS___", {})
    tokens = {k: v for k, v in tokens.items() if now - v.get('created_at', 0) < 3600}
    tokens[token] = {"ip": ip, "created_at": now, "status": "pending", "is_admin": False}
    db["___GETKEY_TOKENS___"] = tokens
    stats = db.get("___FREE_KEY_STATS___", {"total_bypasses": 0})
    stats["total_bypasses"] = stats.get("total_bypasses", 0) + 1
    db["___FREE_KEY_STATS___"] = stats
    save_db(db)
    tg_notify(f"🔗 <b>LINK4M MỚI (API/getkey)</b>\n📍 IP: <code>{ip}</code>\n🔑 Token: <code>{token[:8]}...</code>\n🌐 Link: {short_url}")
    return jsonify({"status": "success", "link": short_url, "token": token})

@app.route('/admin/gen_key_link', methods=['POST'])
def admin_gen_key_link():
    """Admin endpoint — generate link4m link for free key panel."""
    if not session.get('is_admin'):
        return jsonify({"status": "error"}), 401
    ip = get_real_ip()
    db = load_db()
    now = time.time()
    # Tạo token trước, chưa lưu DB
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
    host = os.environ.get('RENDER_EXTERNAL_URL', request.host_url.rstrip('/'))
    dest_url = f"{host}/nhan-key-free?token={token}"
    # Bắt buộc phải có link4m thật — KHÔNG fallback sang URL trực tiếp
    short_url, err = shorten_with_link4m(dest_url)
    if not short_url:
        return jsonify({"status": "error", "message": f"Không tạo được link Link4m. {err}"}), 503
    # Chỉ lưu token vào DB sau khi link4m thành công
    tokens = db.get("___GETKEY_TOKENS___", {})
    tokens = {k: v for k, v in tokens.items() if now - v.get('created_at', 0) < 3600}
    tokens[token] = {"ip": ip, "created_at": now, "status": "pending", "is_admin": True}
    db["___GETKEY_TOKENS___"] = tokens
    stats = db.get("___FREE_KEY_STATS___", {"total_bypasses": 0})
    stats["total_bypasses"] = stats.get("total_bypasses", 0) + 1
    db["___FREE_KEY_STATS___"] = stats
    save_db(db)
    tg_notify(f"🔗 <b>LINK4M MỚI (Admin Panel)</b>\n📍 Admin IP: <code>{ip}</code>\n🔑 Token: <code>{token[:8]}...</code>\n🌐 Link: {short_url}")
    return jsonify({"status": "success", "link": short_url, "token": token})

@app.route('/api/confirm_bypass', methods=['POST'])
def confirm_bypass():
    """Called when user arrives at /nhan-key-free?token=XXX after bypassing link4m."""
    token = request.form.get('token', '').strip()
    client_ip_info = request.form.get('ip_info', '').strip()
    server_ip = get_real_ip()
    if not check_rate_limit(server_ip, max_req=8, window=60):
        return jsonify({"status": "error", "message": "Quá nhiều yêu cầu. Thử lại sau 1 phút!"})
    if not token:
        return jsonify({"status": "error", "message": "Token không hợp lệ! Bạn cần vượt link rút gọn trước."})
    db = load_db()
    now = time.time()
    tokens = db.get("___GETKEY_TOKENS___", {})
    if token not in tokens:
        return jsonify({"status": "error", "message": "Link đã hết hạn hoặc không hợp lệ! Vui lòng lấy link mới từ Admin."})
    token_info = tokens[token]
    if now - token_info.get('created_at', 0) > 3600:
        return jsonify({"status": "error", "message": "Link đã hết hạn (quá 1 giờ)! Vui lòng lấy link mới từ Admin."})
    if token_info.get('status') == 'used':
        existing_key = token_info.get('key', '')
        if existing_key and existing_key in db:
            return jsonify({"status": "success", "key": existing_key, "reused": True, "msg": "Bạn đã nhận key này rồi!"})
        return jsonify({"status": "error", "message": "Link này đã được sử dụng! Vui lòng lấy link mới."})
    is_admin_token = token_info.get('is_admin', False)
    if not is_admin_token:
        # CHECK 3: Bypass detection — token phải được tạo ít nhất 20 giây trước
        elapsed = now - token_info.get('created_at', now)
        if elapsed < 20:
            tg_notify(f"🚨 <b>BYPASS PHÁT HIỆN!</b>\n📍 IP: <code>{server_ip}</code>\n⏱ Elapsed: {elapsed:.1f}s (cần ≥20s)\n🔑 Token: <code>{token[:8]}...</code>\n📊 {client_ip_info[:80] if client_ip_info else '—'}")
            return jsonify({"status": "error", "message": "⚠️ Phát hiện hành vi bypass link! Bạn phải thực sự vượt link rút gọn. Vui lòng lấy link mới và thực hiện đúng!"})
        ip_free_history = db.get("___FREE_IP_HISTORY___", {})
        ip_records = [t for t in ip_free_history.get(server_ip, []) if now - t < 86400]
        if len(ip_records) >= 3:
            return jsonify({"status": "error", "message": "IP này đã đạt giới hạn 3 key/ngày. Thử lại sau 24 giờ!"})
        is_vpn = check_vpn_or_proxy(server_ip)
        if is_vpn:
            return jsonify({"status": "error", "message": "Phát hiện VPN hoặc Proxy! Vui lòng tắt VPN và thử lại để nhận key."})
    cfg = db.get("___FREE_CONFIG___", {"val": 12, "unit": "tiếng", "dev": 9999})
    key_name = f"FREE-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"
    final_info = f"SV IP: {server_ip} | Token: {token[:8]}... | {client_ip_info}"
    db[key_name] = {
        "duration_val": int(cfg.get('val', 12)),
        "duration_unit": cfg.get('unit', 'tiếng'),
        "max_devices": int(cfg.get('dev', 9999)),
        "status": "Chưa kích hoạt",
        "activated_time": None,
        "created_at": now,
        "used_devices": {},
        "creator_info": final_info,
        "client_ip": server_ip
    }
    tokens[token]['status'] = 'used'
    tokens[token]['key'] = key_name
    db["___GETKEY_TOKENS___"] = tokens
    if not is_admin_token:
        ip_free_history = db.get("___FREE_IP_HISTORY___", {})
        ip_records = [t for t in ip_free_history.get(server_ip, []) if now - t < 86400]
        ip_records.append(now)
        ip_free_history[server_ip] = ip_records
        db["___FREE_IP_HISTORY___"] = ip_free_history
    ip_map = db.get("___IP_KEY_MAP___", {})
    ip_map[server_ip] = key_name
    db["___IP_KEY_MAP___"] = ip_map
    save_db(db)
    tg_notify(f"🎉 <b>KEY FREE MỚI CẤP!</b>\n🔑 Key: <code>{key_name}</code>\n📍 IP: <code>{server_ip}</code>\n⏰ {cfg.get('val',12)} {cfg.get('unit','tiếng')} | {cfg.get('dev',1)} thiết bị\n📊 {client_ip_info[:100] if client_ip_info else '—'}")
    return jsonify({"status": "success", "key": key_name, "reused": False})

@app.route('/api/key_stats', methods=['GET'])
def api_key_stats():
    """Returns key statistics for the admin panel stats tab."""
    if not session.get('is_admin'):
        return jsonify({"status": "error"}), 401
    db = load_db()
    now = time.time()
    total = 0
    activated = 0
    expired = 0
    not_activated = 0
    free_total = 0
    for k, v in db.items():
        if k.startswith("___"):
            continue
        if not isinstance(v, dict):
            continue
        total += 1
        if k.startswith("FREE-"):
            free_total += 1
        st = v.get('status', '')
        if st == "Đã kích hoạt":
            _non_perm = [e for e in v.get('used_devices', {}).values() if e != -1]
            is_full = len(v.get('used_devices', {})) >= v.get('max_devices', 1)
            all_exp = len(_non_perm) > 0 and all(now > e for e in _non_perm)
            if is_full and all_exp:
                expired += 1
            else:
                activated += 1
        elif st == "Hết hạn":
            expired += 1
        else:
            not_activated += 1
    stats = db.get("___FREE_KEY_STATS___", {"total_bypasses": 0})
    return jsonify({
        "total": total,
        "activated": activated,
        "expired": expired,
        "not_activated": not_activated,
        "free_total": free_total,
        "total_bypasses": stats.get("total_bypasses", 0)
    })

# ============================================================
#  HTML TEMPLATES
# ============================================================

# ============================================================
# TELEGRAM BOT — Long polling daemon thread + notifications
# ============================================================
TELEGRAM_BOT_TOKEN = '8605090305:AAGMxGBN8dHw3Txi4F8K0Z4WsuBD2ETPBFs'
TELEGRAM_ADMIN_ID = 8401914033
_TG_OFFSET = [0]

def tg_send(chat_id, text, parse_mode='HTML'):
    if not _TG_OK or _req_tg is None:
        return
    try:
        _req_tg.post(
            f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
            json={'chat_id': chat_id, 'text': text[:4000], 'parse_mode': parse_mode, 'disable_web_page_preview': True},
            timeout=10
        )
    except Exception:
        pass

def tg_notify(text):
    tg_send(TELEGRAM_ADMIN_ID, text)

def _tg_handle_cmd(chat_id, text):
    if chat_id != TELEGRAM_ADMIN_ID:
        tg_send(chat_id, '⛔ Bạn không có quyền sử dụng bot này.\nLiên hệ @vkhanh3010 để được hỗ trợ.')
        return
    parts = text.strip().split()
    cmd = parts[0].lower().split('@')[0] if parts else ''
    args = parts[1:]

    if cmd in ('/start', '/menu', '/help'):
        tg_send(chat_id, """🤖 <b>BOT QUẢN LÝ KEY SERVER — VĂN KHÁNH</b>

📊 <b>Thống kê:</b>
/stats — Thống kê tổng quan keys
/link4mstats — Số link4m & key đã lấy
/status — Trạng thái server & DB

🔑 <b>Quản lý Keys VIP:</b>
/keys — 10 VIP keys mới nhất
/newkey [time] [unit] [devices] — Tạo key VIP
  Ví dụ: /newkey 7 ngày 1
/delkey [KEY] — Xóa key
/resetkey [KEY] — Reset key về chưa kích hoạt

🎁 <b>Key Free:</b>
/freekeys — 10 Free keys mới nhất
/genlink — Tạo link Link4m mới (Admin bypass)

🛡️ <b>Bảo mật & DDoS:</b>
/iplog — Nhật ký IP lấy key free
/ddos — Kiểm tra IPs rate-limit bất thường
/resetip [IP] — Reset giới hạn IP

<i>✅ Bot tự thông báo: link4m mới, key cấp, check-device, bypass phát hiện.</i>""")

    elif cmd == '/stats':
        try:
            db = load_db()
            now = time.time()
            total = activated = expired = not_act = free_total = 0
            for k, v in db.items():
                if k.startswith('___') or not isinstance(v, dict): continue
                total += 1
                if k.startswith('FREE-'): free_total += 1
                st = v.get('status', '')
                if st == 'Đã kích hoạt': activated += 1
                elif st == 'Hết hạn': expired += 1
                else: not_act += 1
            stats = db.get('___FREE_KEY_STATS___', {'total_bypasses': 0})
            tokens = db.get('___GETKEY_TOKENS___', {})
            used_tokens = sum(1 for v in tokens.values() if v.get('status') == 'used')
            tg_send(chat_id, f"""📊 <b>THỐNG KÊ HỆ THỐNG KEY</b>

🗄 Tổng keys: <b>{total}</b>
✅ Đã kích hoạt: <b>{activated}</b>
❌ Hết hạn: <b>{expired}</b>
⏳ Chưa kích hoạt: <b>{not_act}</b>
🎁 Keys Free: <b>{free_total}</b>
🔗 Lượt tạo link4m: <b>{stats.get('total_bypasses', 0)}</b>
🔑 Keys đã cấp qua link4m: <b>{used_tokens}</b>""")
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/link4mstats':
        try:
            db = load_db()
            stats = db.get('___FREE_KEY_STATS___', {'total_bypasses': 0})
            tokens = db.get('___GETKEY_TOKENS___', {})
            used = sum(1 for v in tokens.values() if v.get('status') == 'used')
            pending = sum(1 for v in tokens.values() if v.get('status') == 'pending')
            total_bp = stats.get('total_bypasses', 0)
            tg_send(chat_id, f"""🔗 <b>LINK4M STATISTICS</b>

📨 Tổng lượt tạo link: <b>{total_bp}</b>
✅ Đã lấy key thành công: <b>{used}</b>
⏳ Đang chờ (pending): <b>{pending}</b>
❌ Không vượt (bỏ): <b>{max(0, total_bp - used - pending)}</b>""")
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/status':
        try:
            db_size = os.path.getsize(DB_FILE) / 1024 if os.path.exists(DB_FILE) else 0
            host = os.environ.get('RENDER_EXTERNAL_URL', 'localhost')
            with _RATE_LOCK:
                rl_count = len(_RATE_LIMITER)
            now_vn = datetime.now(VN_TZ).strftime('%d/%m/%Y %H:%M:%S')
            tg_send(chat_id, f"""🟢 <b>SERVER STATUS</b>

🌐 Host: <code>{host}</code>
📦 DB Size: <b>{db_size:.1f} KB</b>
🛡 IPs rate-limit đang theo dõi: <b>{rl_count}</b>
⏰ Thời gian VN: <b>{now_vn}</b>""")
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/keys':
        try:
            db = load_db()
            vip_keys = [(k, v) for k, v in db.items() if not k.startswith('___') and isinstance(v, dict) and not k.startswith('FREE-')]
            vip_keys.sort(key=lambda x: x[1].get('created_at', 0), reverse=True)
            if not vip_keys:
                tg_send(chat_id, '📭 Chưa có VIP key nào.')
                return
            lines = ['🔑 <b>10 VIP KEYS MỚI NHẤT:</b>\n']
            for k, v in vip_keys[:10]:
                st = v.get('status', '?')
                icon = '✅' if st == 'Đã kích hoạt' else ('❌' if st == 'Hết hạn' else '⏳')
                lines.append(f'{icon} <code>{k}</code>\n   ⏰ {v.get("duration_val",0)} {v.get("duration_unit","?")} | 📱 {v.get("max_devices",1)} TB')
            tg_send(chat_id, '\n'.join(lines))
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/freekeys':
        try:
            db = load_db()
            free_keys = [(k, v) for k, v in db.items() if not k.startswith('___') and isinstance(v, dict) and k.startswith('FREE-')]
            free_keys.sort(key=lambda x: x[1].get('created_at', 0), reverse=True)
            if not free_keys:
                tg_send(chat_id, '📭 Chưa có Free key nào.')
                return
            lines = ['🎁 <b>10 FREE KEYS MỚI NHẤT:</b>\n']
            for k, v in free_keys[:10]:
                st = v.get('status', '?')
                icon = '✅' if st == 'Đã kích hoạt' else ('❌' if st == 'Hết hạn' else '⏳')
                ip = v.get('client_ip', '?')
                ct = format_ts(v.get('created_at', 0))
                lines.append(f'{icon} <code>{k}</code>\n   📍 IP: <code>{ip}</code> | {ct}')
            tg_send(chat_id, '\n'.join(lines))
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/newkey':
        try:
            if len(args) < 2:
                tg_send(chat_id, '❌ Cú pháp: /newkey [thời_gian] [đơn_vị] [thiết_bị]\nVí dụ: /newkey 7 ngày 1\nĐơn vị: phút, tiếng, ngày, tháng, năm')
                return
            time_val = args[0]
            time_unit = args[1]
            max_dev = int(args[2]) if len(args) > 2 else 1
            if time_unit not in ('phút', 'tiếng', 'ngày', 'tháng', 'năm', 'permanent'):
                tg_send(chat_id, '❌ Đơn vị không hợp lệ! Dùng: phút, tiếng, ngày, tháng, năm')
                return
            db = load_db()
            p1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
            p2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
            pfx = {'ngày': f'{time_val}D', 'tiếng': f'{time_val}H', 'phút': f'{time_val}P', 'tháng': f'{time_val}M', 'năm': f'{time_val}Y', 'permanent': 'VIP'}
            key_name = f"{pfx.get(time_unit, 'KEY')}-{p1}-{p2}"
            db[key_name] = {
                'duration_val': int(time_val) if time_unit != 'permanent' else 0,
                'duration_unit': time_unit, 'max_devices': max_dev, 'status': 'Chưa kích hoạt',
                'activated_time': None, 'created_at': time.time(), 'used_devices': {},
                'creator_info': 'Tạo bởi Admin Bot Telegram'
            }
            save_db(db)
            tg_send(chat_id, f'✅ <b>Tạo key thành công!</b>\n\n🔑 Key: <code>{key_name}</code>\n⏰ Hạn: {time_val} {time_unit}\n📱 Thiết bị: {max_dev}')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi tạo key: {e}\n\nCú pháp: /newkey [thời_gian] [đơn_vị] [thiết_bị]')

    elif cmd == '/delkey':
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /delkey [KEY]')
            return
        key = args[0]
        try:
            db = load_db()
            if key in db and not key.startswith('___'):
                del db[key]
                save_db(db)
                tg_send(chat_id, f'✅ Đã xóa key: <code>{key}</code>')
            else:
                tg_send(chat_id, f'❌ Key không tồn tại: <code>{key}</code>')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/resetkey':
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /resetkey [KEY]')
            return
        key = args[0]
        try:
            db = load_db()
            if key in db and not key.startswith('___'):
                db[key]['status'] = 'Chưa kích hoạt'
                db[key]['activated_time'] = None
                db[key]['used_devices'] = {}
                save_db(db)
                tg_send(chat_id, f'✅ Đã reset key: <code>{key}</code>')
            else:
                tg_send(chat_id, f'❌ Key không tồn tại: <code>{key}</code>')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/genlink':
        try:
            now = time.time()
            token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=20))
            host = os.environ.get('RENDER_EXTERNAL_URL', 'https://localhost')
            dest_url = f"{host}/nhan-key-free?token={token}"
            short_url, err = shorten_with_link4m(dest_url)
            if not short_url:
                tg_send(chat_id, f'❌ Không tạo được link Link4m: {err}')
                return
            db = load_db()
            tokens = db.get('___GETKEY_TOKENS___', {})
            tokens = {k: v for k, v in tokens.items() if now - v.get('created_at', 0) < 3600}
            tokens[token] = {'ip': 'ADMIN_BOT', 'created_at': now - 60, 'status': 'pending', 'is_admin': True}
            db['___GETKEY_TOKENS___'] = tokens
            stats = db.get('___FREE_KEY_STATS___', {'total_bypasses': 0})
            stats['total_bypasses'] = stats.get('total_bypasses', 0) + 1
            db['___FREE_KEY_STATS___'] = stats
            save_db(db)
            tg_send(chat_id, f'🔗 <b>Link Link4m mới (Admin bypass):</b>\n\n<code>{short_url}</code>\n\n⏰ Hết hạn sau 1 giờ\n✅ Admin bypass — không cần VPN check, không cần timing')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi tạo link: {e}')

    elif cmd == '/iplog':
        try:
            db = load_db()
            ip_history = db.get('___FREE_IP_HISTORY___', {})
            now = time.time()
            if not ip_history:
                tg_send(chat_id, '📭 Chưa có nhật ký IP nào.')
                return
            lines = ['📋 <b>NHẬT KÝ IP LẤY KEY FREE (24h):</b>\n']
            recent = [(ip, times) for ip, times in ip_history.items() if any(now - t < 86400 for t in times)]
            recent.sort(key=lambda x: max(x[1]), reverse=True)
            for ip_addr, times in recent[:20]:
                count = len([t for t in times if now - t < 86400])
                last = format_ts(max(times))
                lines.append(f'📍 <code>{ip_addr}</code> — {count} key | {last}')
            tg_send(chat_id, '\n'.join(lines) if len(lines) > 1 else '📭 Không có dữ liệu trong 24h.')
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/ddos':
        try:
            with _RATE_LOCK:
                rl_copy = dict(_RATE_LIMITER)
            now = time.time()
            high = [(ip_addr, len([t for t in times if now - t < 60])) for ip_addr, times in rl_copy.items()]
            high = [(ip_addr, cnt) for ip_addr, cnt in high if cnt >= 3]
            high.sort(key=lambda x: x[1], reverse=True)
            if not high:
                tg_send(chat_id, '✅ Không phát hiện hoạt động DDoS/Rate limit bất thường.')
                return
            lines = [f'⚠️ <b>RATE LIMIT ALERT ({len(high)} IPs):</b>\n']
            for ip_addr, cnt in high[:15]:
                lines.append(f'🔴 <code>{ip_addr}</code> — {cnt} req/60s')
            tg_send(chat_id, '\n'.join(lines))
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    elif cmd == '/resetip':
        if not args:
            tg_send(chat_id, '❌ Cú pháp: /resetip [IP]\nVí dụ: /resetip 1.2.3.4')
            return
        target_ip = args[0]
        try:
            db = load_db()
            changed = []
            ip_history = db.get('___FREE_IP_HISTORY___', {})
            if target_ip in ip_history:
                del ip_history[target_ip]
                db['___FREE_IP_HISTORY___'] = ip_history
                changed.append('Nhật ký IP')
            ip_map = db.get('___IP_KEY_MAP___', {})
            if target_ip in ip_map:
                del ip_map[target_ip]
                db['___IP_KEY_MAP___'] = ip_map
                changed.append('IP-Key map')
            save_db(db)
            msg = f'✅ Đã reset giới hạn cho IP: <code>{target_ip}</code>'
            if changed: msg += f'\nĐã xóa: {", ".join(changed)}'
            tg_send(chat_id, msg)
        except Exception as e:
            tg_send(chat_id, f'❌ Lỗi: {e}')

    else:
        if text.startswith('/'):
            tg_send(chat_id, f'❓ Lệnh không hợp lệ: <code>{cmd}</code>\nGõ /start để xem menu đầy đủ.')

def _tg_poll_worker():
    import time as _tt
    _tt.sleep(10)
    while True:
        try:
            if not _TG_OK or _req_tg is None:
                _tt.sleep(30)
                continue
            resp = _req_tg.get(
                f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates',
                params={'offset': _TG_OFFSET[0], 'timeout': 25, 'allowed_updates': ['message']},
                timeout=32
            )
            data = resp.json()
            if data.get('ok'):
                for upd in data.get('result', []):
                    _TG_OFFSET[0] = upd['update_id'] + 1
                    try:
                        msg = upd.get('message', {})
                        if msg:
                            cid = msg.get('chat', {}).get('id', 0)
                            txt = msg.get('text', '').strip()
                            if txt:
                                _tg_handle_cmd(cid, txt)
                    except Exception:
                        pass
        except Exception:
            _tt.sleep(5)

_tg_thread = threading.Thread(target=_tg_poll_worker, daemon=True)
_tg_thread.start()

# ============================================================
# HTML TEMPLATES
# ============================================================
HTML_P1 = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Server Key Premium</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Inter:wght@400;500;600;700;800&display=swap');
:root {
  --bg: #060b14;
  --panel: rgba(10, 16, 28, 0.92);
  --card: rgba(14, 22, 38, 0.85);
  --border: rgba(0, 200, 255, 0.12);
  --border-h: rgba(0, 200, 255, 0.35);
  --blue: #00c8ff;
  --purple: #a855f7;
  --grad: linear-gradient(135deg, #00c8ff, #a855f7);
  --muted: #6b7a99;
  --text: #e2e8f0;
  --danger: #f43f5e;
  --success: #10d98a;
  --warn: #f59e0b;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; height: 100vh; width: 100vw; display: flex; justify-content: center; align-items: center; overflow: hidden; position: relative; }

/* CANVAS */
#network-canvas { position: fixed; inset: 0; z-index: 0; pointer-events: none; }

/* STARTUP */
#startupLoading {
  position: fixed; inset: 0; background: var(--bg); z-index: 9999;
  display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 18px;
}
.startup-title { font-family: 'Orbitron', sans-serif; font-size: 1.3rem; font-weight: 900; color: var(--blue); letter-spacing: 2px; text-shadow: 0 0 20px rgba(0,200,255,0.5); }
.progress-wrap { width: min(340px, 80vw); }
.progress-track { width: 100%; height: 10px; background: rgba(255,255,255,0.06); border-radius: 99px; overflow: hidden; border: 1px solid rgba(0,200,255,0.2); box-shadow: 0 0 12px rgba(0,200,255,0.08); }
.progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #0ff 0%, #00c8ff 30%, #7c3aed 70%, #a855f7 100%); border-radius: 99px; transition: width 0.12s linear; box-shadow: 0 0 10px rgba(0,200,255,0.6); position: relative; }
.progress-fill::after { content:''; position:absolute; right:0; top:0; bottom:0; width:18px; background: rgba(255,255,255,0.35); border-radius:99px; filter:blur(4px); }
.progress-pct { text-align: center; font-size: 0.82rem; font-weight: 800; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-top: 8px; letter-spacing: 1px; }

/* VIP BADGE */
.vip-badge {
  position: fixed; top: 16px; right: 16px; z-index: 200;
  background: linear-gradient(135deg, #9f1df5, #00c8ff);
  padding: 7px 14px; border-radius: 20px;
  font-size: 0.72rem; font-weight: 800; color: #fff;
  display: flex; align-items: center; gap: 6px;
  box-shadow: 0 0 20px rgba(168, 85, 247, 0.45);
  letter-spacing: 0.4px; text-transform: uppercase;
  animation: badgePulse 2.5s ease infinite;
}
@keyframes badgePulse {
  0%, 100% { box-shadow: 0 0 15px rgba(0,200,255,0.4); }
  50% { box-shadow: 0 0 28px rgba(168,85,247,0.7); }
}

/* HAMBURGER */
.hamburger { position: fixed; top: 16px; left: 20px; z-index: 200; cursor: pointer; display: flex; flex-direction: column; gap: 5px; padding: 6px; }
.hamburger span { display: block; width: 26px; height: 2.5px; border-radius: 4px; background: var(--blue); transition: all 0.3s ease; box-shadow: 0 0 8px rgba(0,200,255,0.5); }
.hamburger span:nth-child(2) { width: 18px; background: var(--purple); box-shadow: 0 0 8px rgba(168,85,247,0.5); }
.hamburger.open span:nth-child(1) { transform: translateY(7.5px) rotate(45deg); }
.hamburger.open span:nth-child(2) { opacity: 0; transform: translateX(-8px); }
.hamburger.open span:nth-child(3) { transform: translateY(-7.5px) rotate(-45deg); }

/* DROPDOWN NAV */
.nav-dropdown {
  position: fixed; top: 58px; left: 16px; z-index: 199;
  background: rgba(8, 14, 26, 0.98); border: 1px solid var(--border-h);
  border-radius: 16px; padding: 8px; min-width: 210px;
  backdrop-filter: blur(20px); box-shadow: 0 12px 40px rgba(0,0,0,0.6);
  display: none; flex-direction: column; gap: 4px;
}
.nav-dropdown.show { display: flex; animation: navIn 0.3s cubic-bezier(0.175,0.885,0.32,1.275); }
@keyframes navIn { from { opacity: 0; transform: translateY(-10px) scale(0.95); } to { opacity: 1; transform: translateY(0) scale(1); } }
.nav-item {
  padding: 11px 14px; border: none; background: transparent; color: var(--muted);
  font-size: 0.83rem; font-weight: 600; cursor: pointer; border-radius: 10px;
  text-align: left; display: flex; align-items: center; gap: 10px;
  transition: all 0.2s ease; font-family: 'Inter', sans-serif;
}
.nav-item i { width: 16px; text-align: center; font-size: 0.9rem; }
.nav-item:hover { color: var(--text); background: rgba(255,255,255,0.06); }
.nav-item.active { background: var(--grad); color: #000; font-weight: 800; }
.nav-item.active i { color: #000; }
.nav-divider { height: 1px; background: rgba(255,255,255,0.07); margin: 4px 0; }
.nav-item-logout { color: var(--danger) !important; }
.nav-item-logout:hover { background: rgba(244,63,94,0.1) !important; color: #ff6b81 !important; }

/* MAIN PANEL */
.panel {
  width: min(500px, 94vw); height: 90vh;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 22px; backdrop-filter: blur(30px);
  box-shadow: 0 30px 80px rgba(0,0,0,0.85), inset 0 1px 0 rgba(255,255,255,0.04);
  display: flex; flex-direction: column; overflow: hidden;
  position: relative; z-index: 5;
}

/* LOGIN */
.login-overlay {
  position: absolute; inset: 0; background: rgba(3, 6, 12, 0.96);
  z-index: 100; display: flex; justify-content: center; align-items: center;
  backdrop-filter: blur(15px); border-radius: 22px;
}
.login-card {
  width: min(360px, 92%); padding: 36px 28px;
  background: var(--card); border: 1px solid var(--border-h);
  border-radius: 20px; text-align: center;
  box-shadow: 0 0 50px rgba(0,200,255,0.1);
}
.login-logo { width: 52px; height: 52px; background: var(--grad); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 18px; font-size: 1.3rem; color: #000; box-shadow: 0 0 25px rgba(0,200,255,0.4); }
.login-title { font-family: 'Orbitron', sans-serif; font-size: 1.2rem; font-weight: 900; margin-bottom: 6px; background: var(--grad); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.login-sub { font-size: 0.78rem; color: var(--muted); margin-bottom: 24px; font-weight: 500; }
.login-err { background: rgba(244,63,94,0.08); border: 1px solid rgba(244,63,94,0.25); color: #fb7185; padding: 10px 12px; border-radius: 10px; font-size: 0.82rem; margin-bottom: 16px; display: none; text-align: left; }

/* HEADER */
.panel-header {
  padding: 0 20px; border-bottom: 1px solid rgba(255,255,255,0.04);
  display: flex; justify-content: center; align-items: center;
  height: 64px; flex-shrink: 0; position: relative;
}
.panel-title { font-family: 'Orbitron', sans-serif; font-size: 1rem; font-weight: 900; color: #fff; letter-spacing: 1.5px; }

/* BODY / SCROLL */
.panel-body { flex: 1; overflow-y: auto; padding: 16px; padding-bottom: 70px; }
.panel-body::-webkit-scrollbar { width: 3px; }
.panel-body::-webkit-scrollbar-thumb { background: rgba(0,200,255,0.2); border-radius: 10px; }

/* TABS */
.tab { display: none; }
.tab.active { display: block; animation: tabIn 0.42s cubic-bezier(0.22, 1, 0.36, 1) both; }
@keyframes tabIn { from { opacity: 0; transform: translateY(16px) scale(0.985); } to { opacity: 1; transform: translateY(0) scale(1); } }

/* CARDS */
.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 18px; margin-bottom: 14px;
}
.card-title {
  font-size: 0.88rem; font-weight: 800; color: #fff;
  display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
}
.card-title i { color: var(--blue); font-size: 0.95rem; }

/* FORMS */
.fg { margin-bottom: 13px; }
.fg label { display: block; font-size: 0.73rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 7px; }
.fg input, .fg select {
  width: 100%; padding: 12px 14px;
  background: rgba(4, 8, 16, 0.8); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 11px; color: var(--text); font-size: 0.88rem; font-weight: 500;
  transition: 0.2s; outline: none; font-family: 'Inter', sans-serif;
}
.fg input:focus, .fg select:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(0,200,255,0.1); }
.fg select option { background: #0a0e1a; }
.radio-row { display: flex; gap: 10px; }
.radio-opt {
  flex: 1; padding: 11px 12px; background: rgba(4,8,16,0.8);
  border: 1px solid rgba(255,255,255,0.08); border-radius: 11px;
  cursor: pointer; display: flex; align-items: center; gap: 8px;
  font-size: 0.82rem; font-weight: 600; color: var(--muted); transition: 0.2s;
}
.radio-opt:has(input:checked) { border-color: var(--blue); color: var(--blue); background: rgba(0,200,255,0.06); }
.radio-opt input { width: 14px; height: 14px; accent-color: var(--blue); }

/* BUTTONS */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 13px 18px; border: none; border-radius: 11px; font-weight: 800; font-size: 0.88rem; cursor: pointer; transition: all 0.2s ease; font-family: 'Inter', sans-serif; letter-spacing: 0.3px; }
.btn-primary { background: var(--grad); color: #000; width: 100%; margin-top: 6px; }
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,200,255,0.35); }
.btn-danger { background: linear-gradient(135deg, #f43f5e, #fb923c); color: #fff; width: 100%; margin-top: 6px; }
.btn-danger:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(244,63,94,0.3); }
.btn-sm { padding: 6px 10px; font-size: 0.73rem; border-radius: 7px; border: 1px solid transparent; background: transparent; cursor: pointer; font-weight: 700; font-family: 'Inter', sans-serif; transition: 0.2s; }
.btn-sm-blue { color: var(--blue); border-color: rgba(0,200,255,0.3); background: rgba(0,200,255,0.06); }
.btn-sm-blue:hover { background: rgba(0,200,255,0.15); }
.btn-sm-warn { color: var(--warn); border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.06); }
.btn-sm-warn:hover { background: rgba(245,158,11,0.15); }
.btn-sm-red { color: var(--danger); border-color: rgba(244,63,94,0.3); background: rgba(244,63,94,0.06); }
.btn-sm-red:hover { background: rgba(244,63,94,0.15); }
.btn-sm-green { color: var(--success); border-color: rgba(16,217,138,0.3); background: rgba(16,217,138,0.06); }
.btn-sm-green:hover { background: rgba(16,217,138,0.15); }

/* BADGES */
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 4px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.badge-yes { background: rgba(16,217,138,0.12); color: var(--success); border: 1px solid rgba(16,217,138,0.25); }
.badge-no { background: rgba(244,63,94,0.12); color: var(--danger); border: 1px solid rgba(244,63,94,0.25); }
.badge-warn { background: rgba(245,158,11,0.12); color: var(--warn); border: 1px solid rgba(245,158,11,0.25); }

/* TABLES */
.tbl-wrap { width: 100%; overflow-x: auto; border-radius: 12px; border: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
th { padding: 11px 12px; background: rgba(4,8,16,0.9); color: var(--blue); font-weight: 700; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.5px; white-space: nowrap; }
td { padding: 11px 12px; border-top: 1px solid rgba(255,255,255,0.03); vertical-align: middle; }
tr:hover td { background: rgba(255,255,255,0.02); }
.key-val { font-weight: 800; color: #fff; font-family: 'Orbitron', sans-serif; font-size: 0.72rem; letter-spacing: 0.5px; }
.td-actions { display: flex; gap: 5px; flex-wrap: wrap; }

/* INFO ROWS */
.info-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.84rem; }
.info-row:last-child { border-bottom: none; }
.info-label { color: var(--muted); font-weight: 600; }
.info-val { color: var(--text); font-weight: 700; text-align: right; }

/* IP BOX */
.ip-box {
  background: rgba(0,200,255,0.04); border: 1px solid var(--border-h);
  border-radius: 14px; padding: 14px; margin-top: 12px; font-size: 0.82rem; line-height: 1.7;
}
.ip-box .ip-header { font-weight: 800; color: var(--blue); display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 0.83rem; text-transform: uppercase; letter-spacing: 0.5px; }
.ip-field { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.ip-field:last-child { border-bottom: none; }
.ip-key { color: var(--muted); font-size: 0.78rem; }
.ip-val { color: var(--text); font-weight: 700; font-size: 0.82rem; }

/* MUSIC PLAYER DJ */
.music-player-card { background: linear-gradient(160deg, rgba(4,8,20,0.98), rgba(10,4,28,0.98)); border: 1px solid rgba(0,200,255,0.25); border-radius: 20px; padding: 16px; margin-bottom: 14px; overflow: hidden; position: relative; }
.music-player-card::before { content:''; position:absolute; inset:0; background:radial-gradient(ellipse at 50% 0%, rgba(0,200,255,0.07) 0%, transparent 70%); pointer-events:none; }
.dj-header { display:flex; align-items:center; gap:8px; margin-bottom:12px; }
.dj-header-title { font-family:'Orbitron',sans-serif; font-size:0.78rem; font-weight:900; color:var(--blue); text-transform:uppercase; letter-spacing:2px; }
.dj-eq-bars { display:flex; align-items:flex-end; gap:2px; height:18px; margin-left:auto; }
.dj-eq-bar { width:3px; border-radius:2px; background:var(--blue); opacity:0.25; transform-origin:bottom; }
.dj-eq-bar.active { opacity:1; animation:eqAnim 0.55s ease-in-out infinite alternate; }
@keyframes eqAnim { from{transform:scaleY(0.25)} to{transform:scaleY(1)} }
.dj-tracks { display:flex; gap:7px; margin-bottom:13px; }
.dj-track-btn { flex:1; padding:8px 5px; border-radius:10px; border:1px solid rgba(255,255,255,0.07); background:rgba(0,0,0,0.3); cursor:pointer; transition:0.2s; text-align:center; min-width:0; }
.dj-track-btn .dt-num { font-family:'Orbitron',sans-serif; font-size:0.6rem; font-weight:900; color:var(--muted); margin-bottom:3px; white-space:nowrap; }
.dj-track-btn .dt-name { font-size:0.72rem; font-weight:700; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.dj-track-btn:hover { border-color:rgba(0,200,255,0.3); background:rgba(0,200,255,0.05); }
.dj-track-btn:hover .dt-num,.dj-track-btn:hover .dt-name { color:var(--text); }
.dj-track-btn.playing { border-color:var(--blue); background:rgba(0,200,255,0.1); box-shadow:0 0 14px rgba(0,200,255,0.18); }
.dj-track-btn.playing .dt-num { color:var(--blue); }
.dj-track-btn.playing .dt-name { color:#fff; font-weight:800; }
.dj-main { display:flex; align-items:center; gap:14px; margin-bottom:13px; }
.vinyl { width:60px; height:60px; flex-shrink:0; border-radius:50%; background:repeating-radial-gradient(#18182a, #18182a 2px, #09090f 3px, #09090f 5px); border:2px solid #2a2a40; display:flex; justify-content:center; align-items:center; box-shadow:0 0 18px rgba(0,200,255,0.22); }
.vinyl-c { width:20px; height:20px; background:var(--grad); border-radius:50%; display:flex; align-items:center; justify-content:center; }
.vinyl.spin { animation:spin 3s linear infinite; }
@keyframes spin { to{transform:rotate(360deg)} }
.dj-info { flex:1; min-width:0; }
.music-title-text { font-family:'Orbitron',sans-serif; font-size:0.76rem; font-weight:900; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; letter-spacing:0.5px; margin-bottom:5px; }
.music-status-text { font-size:0.74rem; color:var(--muted); font-weight:600; }
.dj-controls { display:flex; align-items:center; justify-content:center; gap:10px; margin-bottom:13px; }
.ctrl-btn { width:34px; height:34px; border-radius:50%; border:1px solid rgba(255,255,255,0.1); background:rgba(255,255,255,0.04); cursor:pointer; color:var(--muted); font-size:0.8rem; display:flex; align-items:center; justify-content:center; transition:0.2s; flex-shrink:0; }
.ctrl-btn:hover { border-color:var(--blue); color:var(--blue); background:rgba(0,200,255,0.08); }
.play-btn { width:48px; height:48px; border-radius:50%; background:var(--grad); border:none; cursor:pointer; color:#000; font-size:1rem; display:flex; align-items:center; justify-content:center; flex-shrink:0; transition:0.2s; box-shadow:0 0 20px rgba(0,200,255,0.45); }
.play-btn:hover { transform:scale(1.1); box-shadow:0 0 30px rgba(0,200,255,0.65); }
.music-seek-wrap { }
.seek-bar { width:100%; height:4px; border-radius:99px; background:rgba(255,255,255,0.08); outline:none; -webkit-appearance:none; cursor:pointer; accent-color:var(--blue); display:block; }
.seek-bar::-webkit-slider-thumb { -webkit-appearance:none; width:13px; height:13px; border-radius:50%; background:var(--blue); cursor:pointer; box-shadow:0 0 8px rgba(0,200,255,0.7); }
.seek-times { display:flex; justify-content:space-between; font-size:0.67rem; color:var(--muted); margin-top:5px; font-weight:700; font-family:'Orbitron',sans-serif; }

/* SOCIAL BUTTONS */
.social-btn { display: flex; align-items: center; gap: 12px; padding: 13px 16px; border-radius: 13px; color: #fff; text-decoration: none; font-weight: 700; font-size: 0.85rem; margin-bottom: 9px; transition: all 0.2s ease; position: relative; overflow: hidden; }
.social-btn:hover { transform: translateX(4px); filter: brightness(1.1); }
.social-btn .s-icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; flex-shrink: 0; }
.social-btn .s-text { display: flex; flex-direction: column; gap: 1px; }
.social-btn .s-label { font-size: 0.72rem; font-weight: 600; opacity: 0.75; letter-spacing: 0.3px; text-transform: uppercase; }
.social-btn .s-name { font-size: 0.88rem; font-weight: 800; }
.social-btn .s-arrow { margin-left: auto; opacity: 0.5; font-size: 0.8rem; }
.social-tg { background: linear-gradient(135deg, #0f2744 0%, #1a3a5c 100%); border: 1px solid rgba(34,158,217,0.3); }
.social-tg .s-icon { background: linear-gradient(135deg, #1d8ec3, #229ED9); color: #fff; }
.social-tg:hover { border-color: rgba(34,158,217,0.6); box-shadow: 0 6px 20px rgba(34,158,217,0.2); }
.social-tt { background: linear-gradient(135deg, #0d0d0d 0%, #1a1a2e 100%); border: 1px solid rgba(255,255,255,0.1); }
.social-tt .s-icon { background: linear-gradient(135deg, #010101, #2d2d2d); color: #fff; border: 1px solid #333; }
.social-tt:hover { border-color: rgba(255,255,255,0.25); box-shadow: 0 6px 20px rgba(0,0,0,0.4); }
.social-yt { background: linear-gradient(135deg, #1a0808 0%, #2d1010 100%); border: 1px solid rgba(255,0,0,0.25); }
.social-yt .s-icon { background: linear-gradient(135deg, #c4302b, #ff0000); color: #fff; }
.social-yt:hover { border-color: rgba(255,0,0,0.5); box-shadow: 0 6px 20px rgba(255,0,0,0.2); }
.social-fb { background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%); border: 1px solid rgba(24,119,242,0.3); }
.social-fb .s-icon { background: linear-gradient(135deg, #1877f2, #4293ff); color: #fff; }
.social-fb:hover { border-color: rgba(24,119,242,0.6); box-shadow: 0 6px 20px rgba(24,119,242,0.2); }

/* RESULT BOX */
.result-box { background: rgba(4,8,16,0.9); border: 1px solid var(--border-h); border-radius: 14px; padding: 16px; margin-top: 14px; font-size: 0.85rem; line-height: 1.65; }
.result-title { text-align: center; color: var(--blue); font-weight: 800; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); padding-bottom: 10px; margin-bottom: 14px; }

/* COUNTDOWN */
.countdown-box { background: rgba(0,0,0,0.6); border: 1px dashed rgba(0,200,255,0.3); border-radius: 10px; padding: 10px 14px; margin-top: 8px; font-family: 'Orbitron', sans-serif; font-size: 0.9rem; color: var(--success); text-align: center; }

/* LOADING OVERLAY */
.load-overlay { position: absolute; inset: 0; background: rgba(4,6,12,0.94); z-index: 98; display: none; justify-content: center; align-items: center; flex-direction: column; gap: 12px; backdrop-filter: blur(6px); border-radius: 22px; }
.spinner { width: 36px; height: 36px; border: 3px solid rgba(0,200,255,0.1); border-top-color: var(--blue); border-radius: 50%; animation: spin 0.75s linear infinite; }
.spinner-sm { width: 18px; height: 18px; border-width: 2px; display: inline-block; vertical-align: middle; margin-left: 6px; }

/* FREE LINK BOX */
.free-link-box { background: rgba(16,217,138,0.04); border: 1px dashed rgba(16,217,138,0.3); border-radius: 12px; padding: 14px; margin-top: 14px; }
.free-link-label { font-size: 0.75rem; color: var(--muted); font-weight: 700; margin-bottom: 8px; text-transform: uppercase; }
.free-link-input { width: 100%; padding: 10px 13px; background: rgba(0,0,0,0.5); border: 1px solid rgba(16,217,138,0.2); border-radius: 9px; color: var(--success); font-weight: 700; font-size: 0.85rem; margin-bottom: 8px; cursor: text; }

/* CHANGE PASS CARD */
.change-pass-card { background: linear-gradient(160deg, rgba(168,85,247,0.06), rgba(0,200,255,0.04)); border: 1px solid rgba(168,85,247,0.2); border-radius: 18px; padding: 22px; }
.change-pass-header { text-align: center; margin-bottom: 22px; }
.change-pass-icon { width: 50px; height: 50px; margin: 0 auto 12px; background: linear-gradient(135deg, #a855f7, #00c8ff); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; color: #fff; box-shadow: 0 0 20px rgba(168,85,247,0.4); }
.change-pass-title { font-family: 'Orbitron', sans-serif; font-size: 1rem; font-weight: 900; background: linear-gradient(135deg, #a855f7, #00c8ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.change-pass-sub { font-size: 0.78rem; color: var(--muted); margin-top: 5px; }
.input-with-icon { position: relative; }
.input-with-icon i { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--muted); font-size: 0.85rem; }
.input-with-icon input { padding-left: 38px; }
.change-pass-warn { background: rgba(16,217,138,0.07); border: 1px solid rgba(16,217,138,0.2); border-radius: 10px; padding: 10px 13px; font-size: 0.78rem; color: var(--success); margin-bottom: 14px; display: flex; gap: 8px; align-items: flex-start; }

/* DEV ROW */
.dev-row { background: rgba(0,0,0,0.4); border-radius: 8px; padding: 8px 12px; margin-top: 7px; font-size: 0.78rem; }

/* KEY SEARCH INPUT */
.key-search-wrap { position: relative; }
.key-search-wrap input { padding-right: 50px; }
.key-search-wrap .scan-ip-btn { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: rgba(0,200,255,0.1); border: 1px solid rgba(0,200,255,0.3); color: var(--blue); border-radius: 7px; padding: 5px 9px; font-size: 0.72rem; font-weight: 700; cursor: pointer; transition: 0.2s; }
.key-search-wrap .scan-ip-btn:hover { background: rgba(0,200,255,0.2); }

/* CHECK IP TAB */
.check-ip-result { background: rgba(0,200,255,0.04); border: 1px solid var(--border-h); border-radius: 14px; padding: 16px; margin-top: 14px; display: none; }
.ip-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.ip-info-cell { background: rgba(0,0,0,0.3); border-radius: 10px; padding: 11px 13px; border: 1px solid rgba(255,255,255,0.05); }
.ip-info-cell .ic-label { font-size: 0.68rem; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 4px; }
.ip-info-cell .ic-val { font-size: 0.85rem; font-weight: 800; color: var(--text); word-break: break-all; }
.ip-info-cell.full-width { grid-column: 1 / -1; }

/* DEVICE REVIEW TAB */
.dev-req-card { background: rgba(0,0,0,0.38); border: 1px solid rgba(168,85,247,0.22); border-radius: 14px; padding: 14px 16px; margin-bottom: 10px; transition: border-color 0.2s; }
.dev-req-card:hover { border-color: rgba(168,85,247,0.45); }
.dev-req-device { font-family: 'Orbitron', sans-serif; font-size: 0.75rem; font-weight: 900; color: var(--blue); letter-spacing: 0.5px; word-break: break-all; margin-bottom: 8px; display: flex; align-items: flex-start; gap: 7px; }
.dev-req-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.74rem; color: var(--muted); margin-bottom: 10px; }
.dev-req-meta span { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.05); padding: 3px 8px; border-radius: 6px; }
.dev-req-actions { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }
.badge-pending { background: rgba(245,158,11,0.12); color: var(--warn); border: 1px solid rgba(245,158,11,0.25); display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.badge-approved-dev { background: rgba(16,217,138,0.12); color: var(--success); border: 1px solid rgba(16,217,138,0.25); display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.badge-expired-dev { background: rgba(244,63,94,0.12); color: var(--danger); border: 1px solid rgba(244,63,94,0.25); display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.apv-card { background: rgba(0,0,0,0.38); border: 1px solid rgba(0,200,255,0.15); border-radius: 14px; padding: 13px 16px; margin-bottom: 9px; transition: border-color 0.2s; }
.apv-card:hover { border-color: rgba(0,200,255,0.35); }
.apv-device { font-family: 'Orbitron', sans-serif; font-size: 0.74rem; font-weight: 900; color: #fff; letter-spacing: 0.4px; word-break: break-all; margin-bottom: 7px; }
.apv-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.73rem; color: var(--muted); margin-bottom: 9px; }
.apv-meta span { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.05); padding: 3px 8px; border-radius: 6px; }
.apv-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.dev-empty { text-align: center; padding: 22px 0; color: var(--muted); font-size: 0.83rem; }
.dev-empty i { font-size: 1.6rem; display: block; margin-bottom: 8px; opacity: 0.4; }

/* SETTINGS TAB */
.settings-title { font-family: 'Orbitron', sans-serif; font-size: 1.5rem; font-weight: 900; color: #fff; letter-spacing: 3px; margin-bottom: 18px; text-shadow: 0 0 18px rgba(0,200,100,0.3); }
.ep-outer { background: rgba(4,12,6,0.75); border: 1px solid rgba(0,200,100,0.22); border-radius: 16px; padding: 18px; margin-bottom: 14px; }
.ep-section-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.ep-section-icon { color: #00c864; font-size: 0.95rem; }
.ep-section-name { font-family: 'Courier New', monospace; font-size: 0.82rem; font-weight: 900; color: #00c864; letter-spacing: 1px; text-transform: uppercase; }
.ep-section-desc { font-family: 'Courier New', monospace; font-size: 0.76rem; color: #5a7a6a; line-height: 1.65; margin-bottom: 18px; }
.ep-card { background: rgba(0,0,0,0.45); border: 1px solid rgba(0,200,100,0.15); border-radius: 12px; padding: 16px; margin-bottom: 12px; }
.ep-card:last-child { margin-bottom: 0; }
.ep-method-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.ep-badge-post { background: rgba(0,200,100,0.18); color: #00e878; border: 1px solid rgba(0,200,100,0.5); border-radius: 5px; padding: 3px 9px; font-size: 0.72rem; font-weight: 900; font-family: 'Orbitron', sans-serif; letter-spacing: 1px; }
.ep-path { font-family: 'Courier New', monospace; color: #c8dbd0; font-size: 0.85rem; font-weight: 600; }
.ep-url-row { background: rgba(0,0,0,0.55); border: 1px solid rgba(0,200,100,0.12); border-radius: 9px; padding: 10px 13px; display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
.ep-url-text { flex: 1; font-family: 'Courier New', monospace; font-size: 0.75rem; color: #7eb89a; word-break: break-all; line-height: 1.6; }
.ep-copy-btn { flex-shrink: 0; background: rgba(0,200,100,0.08); border: 1px solid rgba(0,200,100,0.28); color: #00c864; border-radius: 7px; padding: 5px 9px; font-size: 0.72rem; font-weight: 700; cursor: pointer; transition: 0.2s; font-family: 'Inter', sans-serif; }
.ep-copy-btn:hover { background: rgba(0,200,100,0.18); }
.ep-copy-btn.ep-copied { background: rgba(0,200,100,0.22); color: #00ff88; border-color: rgba(0,255,136,0.5); }
.ep-body-label { font-family: 'Courier New', monospace; font-size: 0.64rem; font-weight: 800; color: rgba(0,200,100,0.6); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 7px; }
.ep-body-box { background: rgba(0,0,0,0.55); border: 1px solid rgba(0,200,100,0.1); border-radius: 9px; padding: 12px 14px; font-family: 'Courier New', monospace; font-size: 0.79rem; line-height: 1.8; color: #6a8a7a; }
.ep-jk { color: #7ab8d8; }
.ep-jv { color: #00c864; }
.ep-jb { color: #4a6a5a; }
</style>
</head>
"""

HTML_P2 = """
<body>
<canvas id="network-canvas"></canvas>
<div class="vip-badge"><i class="fa-solid fa-crown"></i> ADMIN VĂN KHÁNH</div>

<!-- STARTUP LOADING -->
<div id="startupLoading">
  <div class="startup-title">ĐANG KẾT NỐI SERVER...</div>
  <div class="progress-wrap">
    <div class="progress-track"><div class="progress-fill" id="pfill"></div></div>
    <div class="progress-pct" id="ppct">0%</div>
  </div>
  <div style="font-size:0.75rem; color: var(--muted); margin-top: 4px;">Vui lòng chờ trong giây lát</div>
</div>
<script>
  (function(){
    var p = 0, tgt = 0, si = 0;
    var steps = [[22,280],[48,420],[68,500],[83,380],[93,450],[98,300],[100,180]];
    function nextStep(){
      if(si >= steps.length) return;
      tgt = steps[si][0];
      setTimeout(nextStep, steps[si][1]);
      si++;
    }
    nextStep();
    function tick(){
      if(p < tgt){ p = Math.min(tgt, p + 1.5); }
      var d = Math.min(100, Math.floor(p));
      document.getElementById('pfill').style.width = d + '%';
      document.getElementById('ppct').innerText = d + '%';
      if(d < 100){ requestAnimationFrame(tick); }
      else { setTimeout(function(){ document.getElementById('startupLoading').style.display='none'; }, 420); }
    }
    requestAnimationFrame(tick);
  })();
</script>

{% if session.get('is_admin') %}
<div class="hamburger" id="hbg" onclick="toggleMenu()"><span></span><span></span><span></span></div>
<div class="nav-dropdown" id="navDrop">
  <button class="nav-item active" onclick="sw('trangchu')"><i class="fa-solid fa-house"></i> Trang Chủ</button>
  <button class="nav-item" onclick="sw('taokhoa')"><i class="fa-solid fa-plus-circle"></i> Tạo Khóa Mới</button>
  <button class="nav-item" onclick="sw('database')"><i class="fa-solid fa-database"></i> Quản Lý Keys</button>
  <button class="nav-item" onclick="sw('checkkey')"><i class="fa-solid fa-shield-halved"></i> Kiểm Tra Key</button>
  <button class="nav-item" onclick="sw('keyfree')"><i class="fa-solid fa-gift"></i> Key Free</button>
  <button class="nav-item" onclick="sw('keystats')"><i class="fa-solid fa-chart-bar"></i> Thống Kê Key</button>
  <button class="nav-item" onclick="sw('quyenriengtu')"><i class="fa-solid fa-lock"></i> Bảo Mật</button>
  <button class="nav-item" onclick="sw('devicereview')"><i class="fa-solid fa-mobile-screen-button"></i> Duyệt Thiết Bị</button>
  <button class="nav-item" onclick="sw('settings')"><i class="fa-solid fa-gear"></i> Settings</button>
  <div class="nav-divider"></div>
  <a href="/logout" class="nav-item nav-item-logout" style="text-decoration:none;"><i class="fa-solid fa-arrow-right-from-bracket"></i> Đăng Xuất</a>
</div>
{% endif %}

<div class="panel">
  <div class="load-overlay" id="loadOverlay">
    <div class="spinner"></div>
    <div style="font-size:0.82rem; color:var(--blue); font-weight:800;">ĐANG XỬ LÝ...</div>
  </div>

  {% if not session.get('is_admin') %}
  <div class="login-overlay">
    <div class="login-card">
      <div class="login-logo"><i class="fa-solid fa-shield-halved"></i></div>
      <div class="login-title">SYSTEM LOGIN</div>
      <div class="login-sub">Nhập thông tin quản trị để tiếp tục</div>
      <div class="login-err" id="loginErr"></div>
      <div id="loginSpinner" style="display:none; padding: 16px 0;"><div class="spinner" style="margin:auto;"></div></div>
      <form id="loginForm">
        <div class="fg" style="text-align:left;">
          <label>Tài khoản</label>
          <div class="input-with-icon"><i class="fa-solid fa-user"></i><input type="text" id="lu" required placeholder="Nhập tài khoản" style="padding-left:38px;"></div>
        </div>
        <div class="fg" style="text-align:left;">
          <label>Mật khẩu</label>
          <div class="input-with-icon"><i class="fa-solid fa-key"></i><input type="password" id="lp" required placeholder="Nhập mật khẩu" style="padding-left:38px;"></div>
        </div>
        <button type="submit" class="btn btn-primary"><i class="fa-solid fa-right-to-bracket"></i> ĐĂNG NHẬP</button>
      </form>
    </div>
  </div>
  {% endif %}

  <div class="panel-header">
    <div class="panel-title">SERVER KEY SYSTEM</div>
  </div>

  <div class="panel-body">
"""

HTML_P3 = """
    <!-- TAB TRANG CHU -->
    <div id="tab-trangchu" class="tab active">
      <div class="card">
        <div class="card-title"><i class="fa-solid fa-link"></i> Mạng Xã Hội Admin</div>
        <a href="https://t.me/vkhanh3010" target="_blank" class="social-btn social-tg">
          <div class="s-icon"><i class="fa-brands fa-telegram"></i></div>
          <div class="s-text"><span class="s-label">Liên hệ</span><span class="s-name">Telegram Admin</span></div>
          <i class="fa-solid fa-chevron-right s-arrow"></i>
        </a>
        <a href="https://www.tiktok.com/@midu.c2?_r=1&_t=ZS-96dFFSbVHBE" target="_blank" class="social-btn social-tt">
          <div class="s-icon"><i class="fa-brands fa-tiktok"></i></div>
          <div class="s-text"><span class="s-label">Follow</span><span class="s-name">Kênh TikTok Chính Thức</span></div>
          <i class="fa-solid fa-chevron-right s-arrow"></i>
        </a>
        <a href="https://youtube.com/@dokimodsgame?si=hrkcwAeZD7UKgKTB" target="_blank" class="social-btn social-yt">
          <div class="s-icon"><i class="fa-brands fa-youtube"></i></div>
          <div class="s-text"><span class="s-label">Subscribe</span><span class="s-name">Kênh YouTube DokiMods</span></div>
          <i class="fa-solid fa-chevron-right s-arrow"></i>
        </a>
        <a href="https://www.facebook.com/share/1ERXsth7Zr/" target="_blank" class="social-btn social-fb">
          <div class="s-icon"><i class="fa-brands fa-facebook-f"></i></div>
          <div class="s-text"><span class="s-label">Theo dõi</span><span class="s-name">Facebook </span></div>
          <i class="fa-solid fa-chevron-right s-arrow"></i>
        </a>
      </div>

      <div class="music-player-card">
        <div class="dj-header">
          <i class="fa-solid fa-compact-disc" style="color:var(--blue);font-size:0.85rem;"></i>
          <div class="dj-header-title">DJ Console</div>
          <div class="dj-eq-bars" id="djEqBars">
            <div class="dj-eq-bar" style="height:60%;animation-delay:0s;"></div>
            <div class="dj-eq-bar" style="height:100%;animation-delay:0.1s;"></div>
            <div class="dj-eq-bar" style="height:40%;animation-delay:0.2s;"></div>
            <div class="dj-eq-bar" style="height:80%;animation-delay:0.15s;"></div>
            <div class="dj-eq-bar" style="height:55%;animation-delay:0.05s;"></div>
            <div class="dj-eq-bar" style="height:90%;animation-delay:0.3s;"></div>
            <div class="dj-eq-bar" style="height:35%;animation-delay:0.25s;"></div>
          </div>
        </div>
        <div class="dj-tracks">
          <div class="dj-track-btn playing" id="track-0" onclick="selectTrack(0)">
            <div class="dt-num">BÀI 1</div>
            <div class="dt-name">Nhạc Nền 1</div>
          </div>
          <div class="dj-track-btn" id="track-1" onclick="selectTrack(1)">
            <div class="dt-num">BÀI 2</div>
            <div class="dt-name">Nhạc Nền 2</div>
          </div>
          <div class="dj-track-btn" id="track-2" onclick="selectTrack(2)">
            <div class="dt-num">BÀI 3</div>
            <div class="dt-name">Nhạc Nền 3</div>
          </div>
        </div>
        <div class="dj-main">
          <div class="vinyl" id="vinylDisk"><div class="vinyl-c"><i class="fa-solid fa-music" style="font-size:0.5rem;color:#000;"></i></div></div>
          <div class="dj-info">
            <div class="music-title-text" id="musicTitle">Nhạc Nền 1</div>
            <div class="music-status-text" id="musicStatus">Đang dừng phát</div>
          </div>
        </div>
        <div class="dj-controls">
          <button class="ctrl-btn" onclick="prevTrack()" title="Bài trước"><i class="fa-solid fa-backward-step"></i></button>
          <button class="ctrl-btn" onclick="seekBack()" title="Tua lùi 10s"><i class="fa-solid fa-rotate-left"></i></button>
          <button class="play-btn" onclick="toggleMusic()"><i class="fa-solid fa-play" id="playIcon"></i></button>
          <button class="ctrl-btn" onclick="seekForward()" title="Tua tiến 10s"><i class="fa-solid fa-rotate-right"></i></button>
          <button class="ctrl-btn" onclick="nextTrack()" title="Bài tiếp"><i class="fa-solid fa-forward-step"></i></button>
        </div>
        <div class="music-seek-wrap">
          <input type="range" class="seek-bar" id="seekBar" value="0" min="0" max="100" step="0.1" oninput="onSeekInput(this.value)">
          <div class="seek-times"><span id="curTime">0:00</span><span id="durTime">0:00</span></div>
        </div>
        <audio id="bgAudio" src="/nhac.mp3"></audio>
      </div>

      {% if session.get('is_admin') %}
      <div class="card" id="ipInfoCard">
        <div class="card-title"><i class="fa-solid fa-globe"></i> Thông Tin IP Của Bạn</div>
        <div id="myIPBox">
          <div style="color:var(--muted); font-size:0.83rem; display:flex; align-items:center; gap:8px;">
            <div class="spinner spinner-sm"></div> Đang quét IP thực...
          </div>
        </div>
      </div>
      {% endif %}
    </div>

    <!-- TAB TẠO KHÓA -->
    <div id="tab-taokhoa" class="tab">
      <div class="card">
        <div class="card-title"><i class="fa-solid fa-wand-magic-sparkles"></i> Tạo Khóa Mới</div>
        <form id="createKeyForm">
          <div class="fg">
            <label>Kiểu tạo</label>
            <div class="radio-row">
              <label class="radio-opt"><input type="radio" name="km" value="random" checked onchange="toggleCustom()"> Random</label>
              <label class="radio-opt"><input type="radio" name="km" value="custom" onchange="toggleCustom()"> Tùy chỉnh</label>
            </div>
          </div>
          <div class="fg" id="customWrap" style="display:none;">
            <label>Mã Key tự nhập</label>
            <input type="text" id="ck" placeholder="VD: VIP-PRO-2026">
          </div>
          <div style="display:flex; gap:10px;">
            <div class="fg" style="flex:1;">
              <label>Thời lượng</label>
              <input type="number" id="tv" value="1" min="1">
            </div>
            <div class="fg" style="flex:1;">
              <label>Đơn vị</label>
              <select id="tu">
                <option value="phút">Phút</option>
                <option value="tiếng">Tiếng</option>
                <option value="ngày" selected>Ngày</option>
                <option value="tháng">Tháng</option>
                <option value="năm">Năm</option>
                <option value="permanent">Vĩnh viễn</option>
              </select>
            </div>
          </div>
          <div class="fg">
            <label>Số thiết bị tối đa</label>
            <input type="number" id="md" value="1" min="1">
          </div>
          <button type="submit" class="btn btn-primary"><i class="fa-solid fa-plus"></i> TẠO KEY NGAY</button>
        </form>
        <div id="createResult" style="display:none; margin-top:12px;"></div>
      </div>
    </div>

    <!-- TAB DATABASE — VIP/FREE sub-tabs -->
    <div id="tab-database" class="tab">
      <div style="display:flex; gap:8px; margin-bottom:12px;">
        <button id="dbTabVipBtn" onclick="switchDbTab('vip')" class="btn btn-primary" style="flex:1;margin-top:0;background:linear-gradient(135deg,rgba(0,200,255,0.18),rgba(168,85,247,0.12));border:1.5px solid rgba(0,200,255,0.4);font-weight:800;"><i class="fa-solid fa-crown" style="color:var(--blue);"></i> VIP Keys</button>
        <button id="dbTabFreeBtn" onclick="switchDbTab('free')" class="btn btn-primary" style="flex:1;margin-top:0;background:rgba(16,217,138,0.07);border:1px solid rgba(16,217,138,0.2);color:var(--success);font-weight:800;"><i class="fa-solid fa-gift"></i> Free Keys</button>
      </div>
      <!-- VIP PANEL -->
      <div id="dbVipPanel" class="card" style="padding:16px 10px;">
        <div class="card-title" style="padding-left:8px;"><i class="fa-solid fa-crown" style="color:var(--blue);"></i> Danh Sách Key VIP</div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Mã Key</th><th>Trạng Thái</th><th>Hạn Dùng</th><th>Thiết Bị</th><th>Ngày Tạo</th><th>Kích Hoạt</th><th>Hành Động</th></tr></thead>
            <tbody id="keyTbl"></tbody>
          </table>
        </div>
      </div>
      <!-- FREE PANEL -->
      <div id="dbFreePanel" class="card" style="padding:16px 10px; display:none;">
        <div class="card-title" style="padding-left:8px;"><i class="fa-solid fa-gift" style="color:var(--success);"></i> Danh Sách Key FREE — IP Đầy Đủ (Admin Only)</div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Mã Key</th><th>IP Nguồn</th><th>Tạo lúc (VN)</th><th>Kích hoạt</th><th>Hạn Dùng</th><th>Thiết Bị</th><th>Trạng Thái</th><th>Hành Động</th></tr></thead>
            <tbody id="dbFreeTbl"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB CHECK KEY -->
    <div id="tab-checkkey" class="tab">
      <div class="card">
        <div class="card-title"><i class="fa-solid fa-magnifying-glass"></i> Kiểm Tra Key</div>
        <form id="checkKeyForm">
          <div class="fg">
            <label>Nhập mã Key cần tra</label>
            <input type="text" id="sk" required placeholder="Nhập key vào đây..." style="width:100%;padding:12px 14px;background:rgba(4,8,16,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:11px;color:var(--text);font-size:0.88rem;font-weight:500;outline:none;font-family:'Inter',sans-serif;transition:0.2s;">
          </div>
          <div style="display:flex; flex-direction:column; align-items:center; gap:9px; margin-bottom:6px;">
            <button type="submit" class="btn btn-primary" style="width:100%; margin-top:0;"><i class="fa-solid fa-search"></i> TRA CỨU KEY</button>
            <button type="button" class="btn btn-primary" style="width:60%; margin-top:0; background:rgba(0,200,255,0.08); color:var(--blue); border:1px solid rgba(0,200,255,0.28);" onclick="scanIPCheck()"><i class="fa-solid fa-location-dot"></i> Quét IP Của Tôi</button>
          </div>
        </form>
        <div id="checkResult" class="result-box" style="display:none;"></div>
        <div id="ipCheckResult" style="display:none; margin-top:10px;"></div>
      </div>
    </div>

    <!-- TAB KEY FREE -->
    <div id="tab-keyfree" class="tab">
      <div class="card">
        <div class="card-title"><i class="fa-solid fa-gear"></i> Cấu Hình Key Free Nhiệm Vụ</div>
        <form id="freeConfigForm">
          <div style="display:flex; gap:10px;">
            <div class="fg" style="flex:1;"><label>Thời gian</label><input type="number" id="fv" value="12" min="1"></div>
            <div class="fg" style="flex:1;"><label>Đơn vị</label><select id="fu"><option value="phút">Phút</option><option value="tiếng" selected>Tiếng</option><option value="ngày">Ngày</option></select></div>
          </div>
          <div class="fg"><label>Số thiết bị tối đa</label><input type="number" id="fd" value="1" min="1"></div>
          <button type="submit" class="btn btn-primary" style="background:linear-gradient(135deg,#10d98a,#00c8ff);"><i class="fa-solid fa-save"></i> LƯU CẤU HÌNH</button>
        </form>
        <div style="margin-top:14px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.05);">
          <div style="font-size:0.75rem; color:var(--muted); margin-bottom:10px; line-height:1.6;"><i class="fa-solid fa-circle-info" style="color:var(--blue); margin-right:5px;"></i> Nhấn nút bên dưới để tạo link rút gọn Link4m. User phải vượt link này mới nhận được key (12 ký tự, hạn 12 giờ, tối đa 3 key/IP/ngày).</div>
          <button type="button" class="btn btn-primary" id="genLinkBtn" onclick="genLink4mLink()" style="background:linear-gradient(135deg,#a855f7,#00c8ff); width:100%;"><i class="fa-solid fa-link"></i> LẤY LINK LINK4M MỚI</button>
        </div>
        <div id="freeLinkBox" style="display:none; margin-top:12px;" class="free-link-box">
          <div class="free-link-label" style="font-size:0.75rem; color:var(--muted); margin-bottom:7px;"><i class="fa-solid fa-link" style="color:var(--blue);"></i> Link rút gọn Link4m (gửi cho User vượt để nhận key):</div>
          <input type="text" id="taskLink" class="free-link-input" readonly style="font-size:0.8rem;">
          <div style="display:flex; gap:8px; margin-top:8px;">
            <button class="btn btn-primary" onclick="copyLink()" style="padding:11px; flex:1;"><i class="fa-solid fa-copy"></i> COPY LINK</button>
            <button class="btn btn-primary" onclick="genLink4mLink()" style="padding:11px; flex:1; background:rgba(168,85,247,0.15); color:var(--purple); border:1px solid rgba(168,85,247,0.3);"><i class="fa-solid fa-rotate"></i> TẠO LINK MỚI</button>
          </div>
          <div style="margin-top:8px; font-size:0.72rem; color:rgba(107,122,153,0.7);"><i class="fa-solid fa-info-circle"></i> Link hết hạn sau 1 giờ. API công khai: <code style="color:var(--blue);">/api/getkey</code></div>
        </div>
      </div>
      <div class="card" style="padding:16px 10px; margin-top:4px;">
        <div class="card-title" style="padding-left:8px;"><i class="fa-solid fa-list-check"></i> Danh Sách Key Free (IP Gốc Ẩn với User)</div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Mã Key</th><th>IP Nguồn (Admin)</th><th>Tạo lúc</th><th>Kích hoạt</th><th>Trạng Thái</th><th>Hành Động</th></tr></thead>
            <tbody id="freeTbl"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB THỐNG KÊ KEY -->
    <div id="tab-keystats" class="tab">
      <div class="card">
        <div class="card-title"><i class="fa-solid fa-chart-bar"></i> Thống Kê Hệ Thống Key</div>
        <div style="display:flex; gap:8px; margin-bottom:16px;">
          <button class="btn btn-primary" style="width:auto; margin-top:0; background:rgba(0,200,255,0.1); color:var(--blue); border:1px solid rgba(0,200,255,0.25);" onclick="loadKeyStats()"><i class="fa-solid fa-rotate"></i> Làm Mới</button>
        </div>
        <div id="keyStatsGrid" style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
          <div style="text-align:center; color:var(--muted); font-size:0.82rem; grid-column:1/-1; padding:20px 0;"><div class="spinner" style="width:24px;height:24px;border-width:2px;margin:0 auto 10px;"></div>Đang tải thống kê...</div>
        </div>
      </div>
      <div class="card" style="margin-top:8px;">
        <div class="card-title"><i class="fa-solid fa-circle-info"></i> API Công Khai — Nhận Key Free (cho Bot / Tool)</div>
        <div style="background:rgba(0,200,255,0.04); border:1px solid rgba(0,200,255,0.15); border-radius:12px; padding:14px 16px; font-size:0.8rem; color:var(--muted); line-height:1.8;">
          <div style="font-weight:800; color:var(--blue); margin-bottom:8px;"><i class="fa-solid fa-code"></i> Endpoint:</div>
          <div style="font-family:'Courier New',monospace; background:rgba(0,0,0,0.4); padding:10px 14px; border-radius:9px; color:var(--success); margin-bottom:10px; word-break:break-all;" id="ep-url-getkey">Loading...</div>
          <div style="font-weight:800; color:var(--blue); margin-bottom:6px;"><i class="fa-solid fa-arrow-right"></i> Method: GET hoặc POST</div>
          <div style="font-weight:800; color:var(--blue); margin-bottom:6px;"><i class="fa-solid fa-arrow-right"></i> Phản hồi:</div>
          <div style="font-family:'Courier New',monospace; background:rgba(0,0,0,0.4); padding:10px 14px; border-radius:9px; color:#6a8a7a; line-height:1.8;">
            <span style="color:#7ab8d8;">"status"</span>: <span style="color:#00c864;">"success"</span>,<br>
            <span style="color:#7ab8d8;">"link"</span>: <span style="color:#00c864;">"https://link4m.com/xxxxxx"</span>,<br>
            <span style="color:#7ab8d8;">"token"</span>: <span style="color:#00c864;">"TOKEN20CHARS"</span>
          </div>
          <div style="margin-top:10px; font-size:0.73rem; color:rgba(107,122,153,0.7);">Giới hạn: 5 lần/30 giây/IP — Tối đa 3 key/IP/24 giờ</div>
        </div>
        <button class="btn btn-primary" onclick="navigator.clipboard.writeText(document.getElementById('ep-url-getkey').innerText).then(()=>alert('Đã copy!'))" style="width:auto; margin-top:10px; background:rgba(0,200,255,0.1); color:var(--blue); border:1px solid rgba(0,200,255,0.25);"><i class="fa-solid fa-copy"></i> COPY URL</button>
      </div>
    </div>

    <!-- TAB QUYỀN RIÊNG TƯ -->
    <div id="tab-quyenriengtu" class="tab">
      <div class="change-pass-card">
        <div class="change-pass-header">
          <div class="change-pass-icon"><i class="fa-solid fa-user-shield"></i></div>
          <div class="change-pass-title">ĐỔI THÔNG TIN QUẢN TRỊ</div>
          <div class="change-pass-sub">Thay đổi tên đăng nhập & mật khẩu. Thông tin được lưu ngay, không đăng xuất.</div>
        </div>
        <div class="change-pass-warn"><i class="fa-solid fa-circle-check" style="margin-top:2px; flex-shrink:0;"></i> Sau khi lưu, bạn vẫn ở lại trang quản trị bình thường.</div>
        <form id="changeAuthForm">
          <div class="fg">
            <label>Tài khoản mới</label>
            <div class="input-with-icon"><i class="fa-solid fa-user"></i><input type="text" id="nu" required placeholder="Nhập tên đăng nhập mới" style="padding-left:38px;"></div>
          </div>
          <div class="fg">
            <label>Mật khẩu mới</label>
            <div class="input-with-icon"><i class="fa-solid fa-lock"></i><input type="password" id="np" required placeholder="Nhập mật khẩu mới" style="padding-left:38px;"></div>
          </div>
          <div class="fg">
            <label>Xác nhận mật khẩu</label>
            <div class="input-with-icon"><i class="fa-solid fa-check-double"></i><input type="password" id="np2" required placeholder="Nhập lại mật khẩu mới" style="padding-left:38px;"></div>
          </div>
          <div id="changeErr" style="display:none; color:var(--danger); font-size:0.8rem; margin-bottom:8px; padding:9px 12px; background:rgba(244,63,94,0.08); border:1px solid rgba(244,63,94,0.2); border-radius:9px;"></div>
          <button type="submit" class="btn btn-primary"><i class="fa-solid fa-floppy-disk"></i> LƯU THAY ĐỔI</button>
        </form>
      </div>
    </div>

    <!-- TAB DUYỆT THIẾT BỊ -->
    <div id="tab-devicereview" class="tab">

      <!-- SECTION 1: YÊU CẦU DUYỆT -->
      <div class="card">
        <div class="card-title" style="border-bottom:1px solid rgba(168,85,247,0.2); padding-bottom:12px; margin-bottom:14px;">
          <i class="fa-solid fa-inbox" style="color:var(--purple);"></i>
          YÊU CẦU DUYỆT
          <span id="devReqBadge" style="display:none; background:var(--danger); color:#fff; font-size:0.68rem; padding:2px 8px; border-radius:20px; margin-left:6px; font-weight:900;"></span>
        </div>
        <div style="display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap;">
          <button class="btn btn-primary" style="width:auto; margin-top:0; background:rgba(168,85,247,0.15); color:var(--purple); border:1px solid rgba(168,85,247,0.3);" onclick="loadDeviceRequests()"><i class="fa-solid fa-rotate"></i> Làm Mới</button>
          <button class="btn btn-primary" style="width:auto; margin-top:0; background:rgba(0,200,255,0.08); color:var(--blue); border:1px solid rgba(0,200,255,0.25); font-size:0.78rem;" onclick="window.open('/dang-ky-thiet-bi','_blank')"><i class="fa-solid fa-external-link-alt"></i> Trang đăng ký</button>
        </div>
        <div id="deviceReqList">
          <div style="color:var(--muted);font-size:0.83rem;text-align:center;padding:22px 0;"><div class="spinner" style="margin:0 auto 10px;width:26px;height:26px;border-width:2px;"></div>Đang tải yêu cầu...</div>
        </div>
      </div>

      <!-- SECTION 2: ĐÃ DUYỆT -->
      <div class="card" style="margin-top:8px;">
        <div class="card-title" style="border-bottom:1px solid rgba(16,217,138,0.2); padding-bottom:12px; margin-bottom:14px;">
          <i class="fa-solid fa-shield-check" style="color:var(--success);"></i>
          ĐÃ DUYỆT
        </div>
        <div style="margin-bottom:10px;">
          <button class="btn btn-primary" style="width:auto; margin-top:0; background:rgba(16,217,138,0.1); color:var(--success); border:1px solid rgba(16,217,138,0.25);" onclick="loadApprovedDevices()"><i class="fa-solid fa-rotate"></i> Làm Mới</button>
        </div>
        <div id="approvedDevList">
          <div style="color:var(--muted);font-size:0.83rem;text-align:center;padding:22px 0;">Đang tải...</div>
        </div>
      </div>

      <!-- SECTION 3: ID ĐÃ DUYỆT — thêm trực tiếp không cần yêu cầu -->
      <div class="card" style="margin-top:8px; background:linear-gradient(160deg,rgba(0,200,255,0.04),rgba(168,85,247,0.04)); border-color:rgba(0,200,255,0.22);">
        <div class="card-title" style="border-bottom:1px solid rgba(0,200,255,0.18); padding-bottom:12px; margin-bottom:16px;">
          <i class="fa-solid fa-circle-plus" style="color:var(--blue);"></i>
          ID ĐÃ DUYỆT — THÊM TRỰC TIẾP
        </div>
        <div style="background:rgba(0,200,255,0.05);border:1px solid rgba(0,200,255,0.15);border-radius:11px;padding:11px 14px;font-size:0.78rem;color:var(--muted);margin-bottom:16px;line-height:1.65;">
          <i class="fa-solid fa-circle-info" style="color:var(--blue);margin-right:5px;"></i>
          Admin có thể thêm Device ID vào danh sách đã duyệt <strong style="color:var(--success);">ngay lập tức</strong> mà không cần người dùng gửi yêu cầu trước.
        </div>
        <form id="adminAddIDForm" onsubmit="doAdminAddID(event)">
          <div class="fg">
            <label><i class="fa-solid fa-fingerprint" style="color:var(--blue);margin-right:5px;"></i> Device ID / Machine ID</label>
            <input type="text" id="adminDeviceId" required placeholder="Dán Device ID của thiết bị vào đây..." style="width:100%;padding:12px 14px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--text);font-size:0.88rem;outline:none;font-family:'Inter',sans-serif;">
          </div>
          <div style="display:flex;gap:10px;">
            <div class="fg" style="flex:1;">
              <label>Thời Gian</label>
              <input type="number" id="adminDevVal" value="7" min="1" style="width:100%;padding:12px 14px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--text);font-size:0.88rem;outline:none;font-family:'Inter',sans-serif;">
            </div>
            <div class="fg" style="flex:1;">
              <label>Đơn Vị</label>
              <select id="adminDevUnit" style="width:100%;padding:12px 14px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--text);font-size:0.88rem;outline:none;font-family:'Inter',sans-serif;">
                <option value="phút">Phút</option>
                <option value="tiếng">Tiếng</option>
                <option value="ngày" selected>Ngày</option>
                <option value="tháng">Tháng</option>
                <option value="năm">Năm</option>
                <option value="permanent">Vĩnh viễn</option>
              </select>
            </div>
          </div>
          <div id="adminAddIDAlert" style="display:none;border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;"></div>
          <button type="submit" id="adminAddIDBtn" class="btn btn-primary" style="background:linear-gradient(135deg,#00c8ff,#a855f7);"><i class="fa-solid fa-circle-plus"></i> DUYỆT & KÍCH HOẠT NGAY</button>
        </form>
        <div style="margin-top:14px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.05);">
          <div style="font-size:0.73rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:8px;"><i class="fa-solid fa-list" style="margin-right:5px;"></i> Tra Cứu Thông Tin IP của Device ID</div>
          <div style="display:flex;gap:9px;">
            <input type="text" id="adminLookupIP" placeholder="Nhập IP hoặc Device ID để tra cứu..." style="flex:1;padding:11px 13px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.08);border-radius:10px;color:var(--text);font-size:0.85rem;outline:none;font-family:'Inter',sans-serif;">
            <button class="btn btn-primary" style="width:auto;margin-top:0;padding:11px 16px;background:rgba(0,200,255,0.1);color:var(--blue);border:1px solid rgba(0,200,255,0.25);" onclick="adminLookupIPInfo()"><i class="fa-solid fa-search"></i></button>
          </div>
          <div id="adminIPLookupResult" style="display:none;margin-top:10px;"></div>
        </div>
      </div>

    </div>

    <!-- TAB SETTINGS -->
    <div id="tab-settings" class="tab">
      <div style="padding: 4px 2px 14px;">
        <div class="settings-title">SETTINGS</div>
      </div>

      <div class="ep-outer">
        <div class="ep-section-header">
          <i class="fa-solid fa-microchip ep-section-icon"></i>
          <span class="ep-section-name">EXTERNAL_API_ENDPOINTS</span>
        </div>
        <div class="ep-section-desc">
          Connect your external tools to these<br>
          endpoints. Copy the URL and use it in your<br>
          app/tool configuration.
        </div>

        <!-- /api/verify -->
        <div class="ep-card">
          <div class="ep-method-row">
            <span class="ep-badge-post">POST</span>
            <span class="ep-path">/api/verify</span>
          </div>
          <div class="ep-url-row">
            <span class="ep-url-text" id="ep-url-verify">Loading...</span>
            <button class="ep-copy-btn" onclick="epCopyUrl('ep-url-verify', this)">
              <i class="fa-solid fa-copy"></i>
            </button>
          </div>
          <div class="ep-body-label">REQUEST_BODY</div>
          <div class="ep-body-box">
            <span class="ep-jb">{</span><br>
            &nbsp;&nbsp;<span class="ep-jk">"key"</span>: <span class="ep-jv">"7DAY-XXXX-XXXX"</span>,<br>
            &nbsp;&nbsp;<span class="ep-jk">"hwid"</span>: <span class="ep-jv">"DEVICE-HWID-STRING"</span><br>
            <span class="ep-jb">}</span>
          </div>
        </div>

        <!-- /api/check-device -->
        <div class="ep-card">
          <div class="ep-method-row">
            <span class="ep-badge-post">POST</span>
            <span class="ep-path">/api/check-device</span>
          </div>
          <div class="ep-url-row">
            <span class="ep-url-text" id="ep-url-check-device">Loading...</span>
            <button class="ep-copy-btn" onclick="epCopyUrl('ep-url-check-device', this)">
              <i class="fa-solid fa-copy"></i>
            </button>
          </div>
          <div class="ep-body-label">REQUEST_BODY</div>
          <div class="ep-body-box">
            <span class="ep-jb">{</span><br>
            &nbsp;&nbsp;<span class="ep-jk">"device_id"</span>: <span class="ep-jv">"PC-GAMER-001"</span><br>
            <span class="ep-jb">}</span>
          </div>
        </div>

      </div>
    </div>

  </div><!-- end panel-body -->
</div><!-- end panel -->
"""

HTML_P5 = """
<script>
// ---- STARTUP NAV ----
function toggleMenu() {
  document.getElementById('hbg').classList.toggle('open');
  document.getElementById('navDrop').classList.toggle('show');
}
function sw(t) {
  document.querySelectorAll('.tab').forEach(el=>el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.remove('active'));
  const tabEl=document.getElementById('tab-'+t);
  if(tabEl) tabEl.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(b=>{ if(b.getAttribute('onclick') && b.getAttribute('onclick').includes("'"+t+"'")) b.classList.add('active'); });
  document.getElementById('hbg').classList.remove('open');
  document.getElementById('navDrop').classList.remove('show');
  if(t==='database' || t==='keyfree') refreshTables();
  if(t==='keyfree') loadFreeConfig();
  if(t==='devicereview'){ loadDeviceRequests(); loadApprovedDevices(); }
  if(t==='settings') initSettingsUrls();
  if(t==='keystats') loadKeyStats();
}

function loadFreeConfig() {
  fetch('/admin/get_free_config').then(r=>r.json()).then(d=>{
    if(d.status==='success'){
      const fv=document.getElementById('fv');
      const fu=document.getElementById('fu');
      const fd=document.getElementById('fd');
      if(fv) fv.value=d.val||'12';
      if(fd) fd.value=d.dev||'1';
      if(fu){
        for(let opt of fu.options){ if(opt.value===d.unit){ opt.selected=true; break; } }
      }
    }
  }).catch(()=>{});
}

// ---- SETTINGS TAB ----
function initSettingsUrls() {
  var origin = window.location.origin;
  var v = document.getElementById('ep-url-verify');
  var c = document.getElementById('ep-url-check-device');
  if(v) v.innerText = origin + '/api/verify';
  if(c) c.innerText = origin + '/api/check-device';
}
function epCopyUrl(id, btn) {
  var el = document.getElementById(id);
  if(!el) return;
  var txt = el.innerText;
  navigator.clipboard.writeText(txt).then(function(){
    var orig = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-check"></i>';
    btn.classList.add('ep-copied');
    setTimeout(function(){ btn.innerHTML = orig; btn.classList.remove('ep-copied'); }, 1500);
  }).catch(function(){ prompt('Copy:', txt); });
}
// Pre-populate URLs on load
(function(){
  var orig = window.location.origin;
  setTimeout(function(){
    var v = document.getElementById('ep-url-verify');
    var c = document.getElementById('ep-url-check-device');
    var g = document.getElementById('ep-url-getkey');
    if(v) v.innerText = orig + '/api/verify';
    if(c) c.innerText = orig + '/api/check-device';
    if(g) g.innerText = orig + '/api/getkey';
  }, 0);
})();

// ---- MUSIC PLAYER (3 TRACKS) ----
const TRACKS = [
  { src: '/nhac.mp3', name: 'Nhạc Nền 1' },
  { src: '/nhac2.mp3', name: 'Nhạc Nền 2' },
  { src: '/nhac3.mp3', name: 'Nhạc Nền 3' }
];
let currentTrack = 0;
const aud = document.getElementById('bgAudio');
let seekDragging = false;

function fmtTime(s) {
  if(isNaN(s)) return '0:00';
  const m = Math.floor(s/60), sec = Math.floor(s%60);
  return m+':'+(sec<10?'0':'')+sec;
}

function selectTrack(idx) {
  const wasPlaying = !aud.paused;
  currentTrack = idx;
  aud.src = TRACKS[idx].src;
  document.getElementById('musicTitle').innerText = TRACKS[idx].name;
  document.querySelectorAll('.dj-track-btn').forEach((el,i)=>{
    el.classList.toggle('playing', i===idx);
  });
  document.getElementById('seekBar').value = 0;
  document.getElementById('curTime').innerText = '0:00';
  document.getElementById('durTime').innerText = '0:00';
  if(wasPlaying) {
    aud.play().then(()=>{ setPlayingUI(true); }).catch(()=>{ setPlayingUI(false); });
  } else {
    setPlayingUI(false);
  }
}

function setPlayingUI(playing) {
  const bars = document.querySelectorAll('.dj-eq-bar');
  if(playing) {
    bars.forEach(b=>b.classList.add('active'));
    document.getElementById('vinylDisk').classList.add('spin');
    document.getElementById('playIcon').className = 'fa-solid fa-pause';
    document.getElementById('musicStatus').innerHTML = "<span style='color:var(--success);'>&#9654; Đang phát</span>";
  } else {
    bars.forEach(b=>b.classList.remove('active'));
    document.getElementById('vinylDisk').classList.remove('spin');
    document.getElementById('playIcon').className = 'fa-solid fa-play';
    document.getElementById('musicStatus').innerHTML = "<span style='color:var(--muted);'>Đang dừng phát</span>";
  }
}

function toggleMusic() {
  if(!aud) return;
  if(aud.paused) {
    aud.play().then(()=>{ setPlayingUI(true); }).catch(()=>{
      document.getElementById('musicStatus').innerHTML = "<span style='color:var(--danger);'>Không tìm thấy file nhạc!</span>";
    });
  } else {
    aud.pause();
    setPlayingUI(false);
  }
}

function prevTrack() {
  selectTrack((currentTrack - 1 + TRACKS.length) % TRACKS.length);
}
function nextTrack() {
  selectTrack((currentTrack + 1) % TRACKS.length);
}
function seekBack() {
  aud.currentTime = Math.max(0, aud.currentTime - 10);
}
function seekForward() {
  aud.currentTime = Math.min(aud.duration || 0, aud.currentTime + 10);
}
function onSeekInput(v) {
  seekDragging = true;
  if(aud.duration) aud.currentTime = (v/100)*aud.duration;
}

aud.addEventListener('timeupdate', ()=>{
  if(!seekDragging && aud.duration) {
    const pct = (aud.currentTime / aud.duration) * 100;
    document.getElementById('seekBar').value = pct;
    document.getElementById('curTime').innerText = fmtTime(aud.currentTime);
    document.getElementById('durTime').innerText = fmtTime(aud.duration);
  }
});
aud.addEventListener('loadedmetadata', ()=>{
  document.getElementById('durTime').innerText = fmtTime(aud.duration);
});
aud.addEventListener('ended', ()=>{ nextTrack(); });
document.getElementById('seekBar').addEventListener('mouseup', ()=>{ seekDragging=false; });
document.getElementById('seekBar').addEventListener('touchend', ()=>{ seekDragging=false; });

// ---- LOGIN ----
const lf = document.getElementById('loginForm');
if(lf) {
  lf.addEventListener('submit', e=>{
    e.preventDefault();
    lf.style.display='none';
    document.getElementById('loginSpinner').style.display='block';
    setTimeout(()=>{
      fetch('/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`user=${encodeURIComponent(document.getElementById('lu').value)}&pass=${encodeURIComponent(document.getElementById('lp').value)}`})
      .then(r=>r.json()).then(d=>{
        if(d.status==='success') location.reload();
        else {
          lf.style.display='block';
          document.getElementById('loginSpinner').style.display='none';
          const e=document.getElementById('loginErr'); e.innerText=d.message; e.style.display='block';
        }
      });
    },1000);
  });
}

// ---- CHANGE ADMIN (no logout) ----
const caf = document.getElementById('changeAuthForm');
if(caf) {
  caf.addEventListener('submit', e=>{
    e.preventDefault();
    const u=document.getElementById('nu').value.trim();
    const p=document.getElementById('np').value.trim();
    const p2=document.getElementById('np2').value.trim();
    const errEl=document.getElementById('changeErr');
    if(p !== p2) { errEl.innerText='Mật khẩu xác nhận không khớp!'; errEl.style.display='block'; return; }
    if(!u || !p) { errEl.innerText='Tài khoản và mật khẩu không được để trống!'; errEl.style.display='block'; return; }
    errEl.style.display='none';
    fetch('/api/change_admin',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`u=${encodeURIComponent(u)}&p=${encodeURIComponent(p)}`})
    .then(r=>r.json()).then(d=>{
      if(d.status==='success') {
        errEl.style.cssText='display:block;color:var(--success);background:rgba(16,217,138,0.08);border-color:rgba(16,217,138,0.25);';
        errEl.innerHTML='<i class="fa-solid fa-check-circle"></i> Đổi thành công! Thông tin đã được cập nhật.';
        caf.reset();
        setTimeout(()=>{ errEl.style.display='none'; },3000);
      } else {
        errEl.style.cssText='display:block;';
        errEl.innerText=d.message||'Lỗi hệ thống!';
      }
    });
  });
}

// ---- CREATE KEY ----
function toggleCustom() {
  document.getElementById('customWrap').style.display = document.querySelector('input[name="km"]:checked').value==='custom'?'block':'none';
}
const ckf = document.getElementById('createKeyForm');
if(ckf) {
  ckf.addEventListener('submit', e=>{
    e.preventDefault();
    document.getElementById('loadOverlay').style.display='flex';
    const payload=`mode=${document.querySelector('input[name="km"]:checked').value}&v=${document.getElementById('tv').value}&u=${document.getElementById('tu').value}&d=${document.getElementById('md').value}&c_key=${encodeURIComponent(document.getElementById('ck').value||'')}`;
    fetch('/admin',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:payload})
    .then(r=>r.json()).then(d=>{
      document.getElementById('loadOverlay').style.display='none';
      if(d.status==='success') {
        const cr=document.getElementById('createResult');
        cr.style.display='block';
        cr.innerHTML=`<div style="background:rgba(16,217,138,0.08);border:1px solid rgba(16,217,138,0.25);border-radius:11px;padding:12px 15px;font-size:0.83rem;">
          <div style="color:var(--success);font-weight:800;margin-bottom:6px;"><i class="fa-solid fa-check-circle"></i> Tạo Key thành công!</div>
          <div style="color:#fff;font-family:'Orbitron',sans-serif;font-size:0.95rem;letter-spacing:1px;">${d.key||''}</div>
          <button onclick="copyText('${d.key||''}', this)" class="btn-sm btn-sm-blue" style="margin-top:8px;"><i class="fa-solid fa-copy"></i> Copy Key</button>
        </div>`;
        ckf.reset(); toggleCustom();
        setTimeout(()=>{ sw('database'); },1500);
      }
    });
  });
}

// ---- DB TAB SWITCH ----
function switchDbTab(tab) {
  const vipP=document.getElementById('dbVipPanel');
  const freeP=document.getElementById('dbFreePanel');
  const vipB=document.getElementById('dbTabVipBtn');
  const freeB=document.getElementById('dbTabFreeBtn');
  if(tab==='vip'){
    if(vipP) vipP.style.display='';
    if(freeP) freeP.style.display='none';
    if(vipB){vipB.style.border='1.5px solid rgba(0,200,255,0.5)';vipB.style.background='linear-gradient(135deg,rgba(0,200,255,0.22),rgba(168,85,247,0.14))';}
    if(freeB){freeB.style.border='1px solid rgba(16,217,138,0.2)';freeB.style.background='rgba(16,217,138,0.07)';}
  } else {
    if(vipP) vipP.style.display='none';
    if(freeP) freeP.style.display='';
    if(freeB){freeB.style.border='1.5px solid rgba(16,217,138,0.5)';freeB.style.background='rgba(16,217,138,0.16)';}
    if(vipB){vipB.style.border='1px solid rgba(0,200,255,0.25)';vipB.style.background='rgba(0,200,255,0.07)';}
  }
  refreshTables();
}

// ---- TABLES ----
let countdownInterval = null;
function refreshTables() {
  fetch('/api/list_keys').then(r=>r.json()).then(data=>{
    const kt=document.getElementById('keyTbl');
    const ft=document.getElementById('freeTbl');
    const dft=document.getElementById('dbFreeTbl');
    if(kt) kt.innerHTML='';
    if(ft) ft.innerHTML='';
    if(dft) dft.innerHTML='';
    const now=Date.now()/1000;
    data.forEach(i=>{
      const sc=i.status==='Đã kích hoạt'?'badge-yes':(i.status==='Chưa kích hoạt'?'badge-warn':'badge-no');
      if(!i.is_free && kt) {
        kt.innerHTML+=`<tr>
          <td><span class="key-val">${i.key}</span></td>
          <td><span class="badge ${sc}">${i.status}</span></td>
          <td style="color:var(--muted);">${i.han_dung}</td>
          <td style="color:var(--purple); font-weight:800;">${i.thiet_bi}</td>
          <td style="color:var(--muted); font-size:0.75rem; white-space:nowrap;">${i.created_at_str}</td>
          <td style="color:var(--muted); font-size:0.75rem; white-space:nowrap;">${i.activated_time_str}</td>
          <td><div class="td-actions">
            <button class="btn-sm btn-sm-blue" onclick="copyText('${i.key}',this)"><i class="fa-solid fa-copy"></i></button>
            <button class="btn-sm btn-sm-warn" onclick="resetKey('${i.key}')"><i class="fa-solid fa-rotate"></i></button>
            <button class="btn-sm btn-sm-red" onclick="delKey('${i.key}')"><i class="fa-solid fa-trash"></i></button>
          </div></td>
        </tr>`;
      }
      if(i.is_free) {
        const ip=i.client_ip||i.creator_info||'—';
        const isNew = i.age_hours < 12;
        const freeRow=`<tr>
          <td><span class="key-val" style="color:var(--success);font-size:0.78rem;">${i.key}</span></td>
          <td style="font-size:0.73rem; color:var(--blue); max-width:140px; white-space:normal; word-break:break-all; font-weight:700;"><i class="fa-solid fa-location-dot" style="margin-right:3px;"></i>${ip}</td>
          <td style="color:var(--muted); font-size:0.73rem; white-space:nowrap;">${i.created_at_str}</td>
          <td style="color:var(--muted); font-size:0.73rem; white-space:nowrap;">${i.activated_time_str}</td>
          <td style="color:var(--muted); font-size:0.73rem;">${i.han_dung}</td>
          <td style="color:var(--purple); font-weight:800; font-size:0.75rem;">${i.thiet_bi}</td>
          <td><span class="badge ${sc}">${i.status}</span></td>
          <td><div class="td-actions">
            <button class="btn-sm btn-sm-blue" onclick="copyText('${i.key}',this)"><i class="fa-solid fa-copy"></i></button>
            ${isNew?`<button class="btn-sm btn-sm-green" onclick="regenFreeKey('${i.client_ip||''}','${i.key}')" title="Tạo lại key"><i class="fa-solid fa-arrows-rotate"></i></button>`:''}
            <button class="btn-sm btn-sm-red" onclick="delKey('${i.key}')"><i class="fa-solid fa-trash"></i></button>
          </div></td>
        </tr>`;
        if(dft) dft.innerHTML+=freeRow;
        if(ft) {
          ft.innerHTML+=`<tr>
            <td><span class="key-val" style="color:var(--blue);">${i.key}</span></td>
            <td style="font-size:0.73rem; color:var(--muted); max-width:160px; white-space:normal; word-break:break-all;">${i.creator_info||'—'}</td>
            <td style="color:var(--muted); font-size:0.75rem; white-space:nowrap;">${i.created_at_str}</td>
            <td style="color:var(--muted); font-size:0.75rem; white-space:nowrap;">${i.activated_time_str}</td>
            <td><span class="badge ${sc}">${i.status}</span></td>
            <td><div class="td-actions">
              <button class="btn-sm btn-sm-blue" onclick="copyText('${i.key}',this)"><i class="fa-solid fa-copy"></i></button>
              ${isNew?`<button class="btn-sm btn-sm-green" onclick="regenFreeKey('${i.client_ip||''}','${i.key}')"><i class="fa-solid fa-arrows-rotate"></i></button>`:''}
              <button class="btn-sm btn-sm-red" onclick="delKey('${i.key}')"><i class="fa-solid fa-trash"></i></button>
            </div></td>
          </tr>`;
        }
      }
    });
  });
}

function regenFreeKey(ip, oldKey) {
  if(!confirm(`Tạo lại key mới cho IP: ${ip||'?'} và xóa key cũ [${oldKey}]?`)) return;
  fetch('/api/regen_free_key',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`ip=${encodeURIComponent(ip)}`})
  .then(r=>r.json()).then(d=>{ if(d.status==='success'){alert('Đã tạo key mới: '+d.key); refreshTables();} });
}

// ---- COUNTDOWN ----
setInterval(()=>{
  document.querySelectorAll('.free-cd').forEach(el=>{
    const exp=parseFloat(el.getAttribute('data-exp'));
    if(isNaN(exp)) return;
    if(exp===-1){ el.innerHTML='Vĩnh viễn'; return; }
    const now=Date.now()/1000, diff=exp-now;
    if(diff<=0){ el.innerHTML="<span style='color:var(--danger);'>Đã hết hạn</span>"; return; }
    const d=Math.floor(diff/86400),h=Math.floor((diff%86400)/3600),m=Math.floor((diff%3600)/60),s=Math.floor(diff%60);
    el.innerHTML=`<span style='color:var(--success);'>Còn ${d>0?d+' ngày ':''} ${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}</span>`;
  });
},1000);

// ---- KEY ACTIONS ----
function copyText(txt, btn) {
  navigator.clipboard.writeText(txt);
  if(btn){ const orig=btn.innerHTML; btn.innerHTML='<i class="fa-solid fa-check"></i>'; setTimeout(()=>btn.innerHTML=orig,1200); }
}
function delKey(k) {
  if(confirm(`Xóa vĩnh viễn key [${k}] khỏi hệ thống?`)) fetch(`/delete/${k}`).then(()=>refreshTables());
}
function resetKey(k) {
  if(confirm(`Đưa key [${k}] về trạng thái Chưa Kích Hoạt?`)) fetch(`/reset/${k}`).then(()=>{ refreshTables(); });
}

// ---- FREE CONFIG ----
const fcf=document.getElementById('freeConfigForm');
if(fcf){
  fcf.addEventListener('submit', e=>{
    e.preventDefault();
    const btn=e.submitter||document.querySelector('#freeConfigForm button[type=submit]');
    const origHTML=btn?btn.innerHTML:'';
    if(btn){btn.disabled=true;btn.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';}
    fetch('/admin/free_setup',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`v=${document.getElementById('fv').value}&u=${document.getElementById('fu').value}&d=${document.getElementById('fd').value}`})
    .then(r=>r.json()).then(d=>{
      if(btn){btn.disabled=false;btn.innerHTML=origHTML;}
      if(d.status==='success'){
        if(btn){btn.innerHTML='<i class="fa-solid fa-check"></i> ĐÃ LƯU';setTimeout(()=>{btn.innerHTML=origHTML;},1500);}
      }
    }).catch(()=>{if(btn){btn.disabled=false;btn.innerHTML=origHTML;}});
  });
}

function genLink4mLink(){
  const btn=document.getElementById('genLinkBtn');
  if(btn){btn.disabled=true;btn.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Đang tạo link Link4m...';}
  fetch('/admin/gen_key_link',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:''})
  .then(r=>r.json()).then(d=>{
    if(btn){btn.disabled=false;btn.innerHTML='<i class="fa-solid fa-link"></i> LẤY LINK LINK4M MỚI';}
    if(d.status==='success'){
      const lb=document.getElementById('freeLinkBox');
      lb.style.display='block';
      document.getElementById('taskLink').value=d.link;
    } else {
      alert('Lỗi: '+(d.message||'Không tạo được link!'));
    }
  }).catch(()=>{
    if(btn){btn.disabled=false;btn.innerHTML='<i class="fa-solid fa-link"></i> LẤY LINK LINK4M MỚI';}
    alert('Lỗi kết nối máy chủ. Thử lại!');
  });
}

function copyLink(){
  const val=document.getElementById('taskLink').value;
  if(!val) return;
  navigator.clipboard.writeText(val).then(()=>alert('✅ Đã copy link Link4m! Gửi cho User để vượt nhận key.')).catch(()=>prompt('Copy:',val));
}

function loadKeyStats(){
  const grid=document.getElementById('keyStatsGrid');
  const urlEl=document.getElementById('ep-url-getkey');
  if(urlEl) urlEl.innerText=window.location.origin+'/api/getkey';
  if(!grid) return;
  grid.innerHTML='<div style="text-align:center;color:var(--muted);font-size:0.82rem;grid-column:1/-1;padding:20px 0;"><div class="spinner" style="width:24px;height:24px;border-width:2px;margin:0 auto 10px;"></div>Đang tải thống kê...</div>';
  fetch('/api/key_stats').then(r=>r.json()).then(d=>{
    const card=(icon,label,val,color)=>`<div style="background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:16px;text-align:center;">
      <div style="font-size:1.5rem;color:${color};margin-bottom:6px;"><i class="fa-solid ${icon}"></i></div>
      <div style="font-family:'Orbitron',sans-serif;font-size:1.4rem;font-weight:900;color:${color};">${val}</div>
      <div style="font-size:0.72rem;color:var(--muted);margin-top:4px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">${label}</div>
    </div>`;
    grid.innerHTML=
      card('fa-database','Tổng Keys',d.total,'var(--blue)')+
      card('fa-circle-check','Đã Kích Hoạt',d.activated,'var(--success)')+
      card('fa-circle-xmark','Hết Hạn',d.expired,'var(--danger)')+
      card('fa-clock','Chưa Kích Hoạt',d.not_activated,'var(--warn)')+
      card('fa-gift','Keys Free',d.free_total,'var(--purple)')+
      card('fa-link','Lượt Vượt Link',d.total_bypasses,'#00c8ff');
  }).catch(()=>{
    if(grid) grid.innerHTML='<div style="color:var(--danger);text-align:center;grid-column:1/-1;padding:16px;font-size:0.82rem;"><i class="fa-solid fa-triangle-exclamation"></i> Lỗi tải thống kê!</div>';
  });
}

// ---- CHECK KEY ----
const ckForm=document.getElementById('checkKeyForm');
if(ckForm){
  ckForm.addEventListener('submit', e=>{
    e.preventDefault();
    const b=document.getElementById('checkResult'); b.style.display='block';
    b.innerHTML=`<div style="display:flex;align-items:center;gap:10px;"><div class="spinner spinner-sm" style="width:22px;height:22px;border-width:2px;"></div><span style="color:var(--blue);font-weight:700;font-size:0.84rem;">Đang truy xuất dữ liệu...</span></div>`;
    setTimeout(()=>{
      fetch('/',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`key=${encodeURIComponent(document.getElementById('sk').value)}`})
      .then(r=>r.json()).then(d=>{
        if(d.exists){
          const sc=d.key_status==='Đã kích hoạt'?'badge-yes':(d.key_status==='Chưa kích hoạt'?'badge-warn':'badge-no');
          let devHtml='';
          if(d.key_status==='Đã kích hoạt'){
            for(let did in d.dev_dict){
              devHtml+=`<div class="dev-row"><div style="color:var(--muted);font-size:0.76rem;">Thiết bị: <span style="color:var(--purple);">${did.substring(0,12)}...</span></div><div class="free-cd" data-exp="${d.dev_dict[did]}" style="font-size:0.82rem;margin-top:3px;">Đang tính...</div></div>`;
            }
            if(!devHtml) devHtml=`<div class="dev-row" style="color:var(--muted);font-size:0.82rem;">Chưa có thiết bị nào kích hoạt</div>`;
          }
          b.innerHTML=`<div class="result-title"><i class="fa-solid fa-database"></i> KẾT QUẢ TRA CỨU KEY</div>
            <div class="info-row"><span class="info-label">Mã Key</span><span class="info-val" style="font-family:'Orbitron',sans-serif;font-size:0.82rem;">${d.key}</span></div>
            <div class="info-row"><span class="info-label">Trạng thái</span><span class="badge ${sc}">${d.key_status}</span></div>
            <div class="info-row"><span class="info-label">Hạn dùng</span><span class="info-val">${d.duration}</span></div>
            <div class="info-row"><span class="info-label">Ngày tạo</span><span class="info-val">${d.created_at}</span></div>
            <div class="info-row"><span class="info-label">Kích hoạt lúc</span><span class="info-val">${d.activated_time}</span></div>
            <div class="info-row"><span class="info-label">Thiết bị</span><span class="info-val" style="color:var(--purple);">${d.used_devices}/${d.max_devices}</span></div>
            ${devHtml}`;
        } else {
          b.innerHTML=`<div style="text-align:center; color:var(--danger); font-weight:800;"><i class="fa-solid fa-triangle-exclamation"></i> ${d.msg}</div>`;
        }
      });
    },500);
  });
}

// ---- IP SCAN ON ADMIN HOME ----
function scanAndShowIP(targetEl) {
  fetch('https://get.geojs.io/v1/ip/geo.json')
  .then(r=>r.json()).then(d=>{
    if(d && d.ip){
      targetEl.innerHTML=`<div class="ip-box">
        <div class="ip-header"><i class="fa-solid fa-location-dot"></i> Thông tin IP thực của bạn</div>
        <div class="ip-field"><span class="ip-key">Địa chỉ IP</span><span class="ip-val" style="color:var(--success);">${d.ip}</span></div>
        <div class="ip-field"><span class="ip-key">Quốc gia</span><span class="ip-val">${d.country||'—'}</span></div>
        <div class="ip-field"><span class="ip-key">Thành phố</span><span class="ip-val">${d.city||'—'}</span></div>
        <div class="ip-field"><span class="ip-key">ISP/Tổ chức</span><span class="ip-val">${d.organization_name||d.org||'—'}</span></div>
        <div class="ip-field" style="border:none;padding-top:8px;">
          <a href="https://www.google.com/maps?q=${d.latitude},${d.longitude}" target="_blank" style="color:var(--purple);text-decoration:none;font-weight:700;font-size:0.8rem;border:1px solid rgba(168,85,247,0.3);padding:4px 10px;border-radius:7px;display:inline-flex;align-items:center;gap:5px;">
            <i class="fa-solid fa-map-location-dot"></i> Xem bản đồ Google
          </a>
        </div>
      </div>`;
    }
  }).catch(()=>{
    targetEl.innerHTML=`<div style="color:var(--danger);font-size:0.82rem;"><i class="fa-solid fa-shield-halved"></i> Tường lửa chặn quét IP. Thử lại sau.</div>`;
  });
}

const myIPBox = document.getElementById('myIPBox');
if(myIPBox) scanAndShowIP(myIPBox);

// ---- IP CHECK IN SEARCH ----
let scannedIP = '';
function scanIPCheck() {
  const ipR=document.getElementById('ipCheckResult');
  ipR.style.display='block';
  ipR.innerHTML=`<div style="display:flex;align-items:center;gap:8px;color:var(--muted);font-size:0.8rem;"><div class="spinner spinner-sm" style="width:16px;height:16px;border-width:2px;"></div> Đang quét IP...</div>`;
  fetch('https://get.geojs.io/v1/ip/geo.json')
  .then(r=>r.json()).then(d=>{
    if(d && d.ip){
      scannedIP=d.ip;
      ipR.innerHTML=`<div class="ip-box" style="margin-top:0;">
        <div class="ip-header"><i class="fa-solid fa-location-dot"></i> IP của bạn khi check</div>
        <div class="ip-field"><span class="ip-key">Địa chỉ IP</span><span class="ip-val" style="color:var(--success);">${d.ip}</span></div>
        <div class="ip-field"><span class="ip-key">Quốc gia</span><span class="ip-val">${d.country||'—'}</span></div>
        <div class="ip-field"><span class="ip-key">Thành phố</span><span class="ip-val">${d.city||'—'}</span></div>
        <div class="ip-field"><span class="ip-key">ISP</span><span class="ip-val">${d.organization_name||d.org||'—'}</span></div>
      </div>`;
    }
  }).catch(()=>{
    ipR.innerHTML=`<div style="color:var(--danger);font-size:0.8rem;padding:8px;">Không thể quét IP.</div>`;
  });
}

// ---- CHECK IP TAB ----
function renderIPResult(d) {
  const grid = document.getElementById('ipInfoGrid');
  const mapDiv = document.getElementById('ipMapLink');
  const resBox = document.getElementById('ipScanResult');
  resBox.style.display = 'block';

  const unknown = '— Không rõ —';
  const countryMap = {
    'Vietnam':'Việt Nam','United States':'Hoa Kỳ','China':'Trung Quốc','Japan':'Nhật Bản',
    'South Korea':'Hàn Quốc','Singapore':'Singapore','Thailand':'Thái Lan',
    'Germany':'Đức','France':'Pháp','United Kingdom':'Anh','Australia':'Úc',
    'Canada':'Canada','Russia':'Nga','India':'Ấn Độ','Brazil':'Brazil',
    'Indonesia':'Indonesia','Malaysia':'Malaysia','Philippines':'Philippines',
    'Taiwan':'Đài Loan','Hong Kong':'Hồng Kông'
  };
  const translateCountry = c => countryMap[c] || c || unknown;

  grid.innerHTML = `
    <div class="ip-info-cell full-width">
      <div class="ic-label">Địa Chỉ IP</div>
      <div class="ic-val" style="color:var(--success); font-family:'Orbitron',sans-serif; font-size:1rem;">${d.ip || unknown}</div>
    </div>
    <div class="ip-info-cell">
      <div class="ic-label">Quốc Gia</div>
      <div class="ic-val">${translateCountry(d.country)} ${d.country_code?'('+d.country_code+')':''}</div>
    </div>
    <div class="ip-info-cell">
      <div class="ic-label">Thành Phố</div>
      <div class="ic-val">${d.city || unknown}</div>
    </div>
    <div class="ip-info-cell">
      <div class="ic-label">Khu Vực</div>
      <div class="ic-val">${d.region || d.timezone_region || unknown}</div>
    </div>
    <div class="ip-info-cell">
      <div class="ic-label">Múi Giờ</div>
      <div class="ic-val">${d.timezone || unknown}</div>
    </div>
    <div class="ip-info-cell full-width">
      <div class="ic-label">Nhà Mạng / Tổ Chức</div>
      <div class="ic-val" style="color:var(--blue);">${d.organization_name || d.org || unknown}</div>
    </div>
    <div class="ip-info-cell">
      <div class="ic-label">Vĩ Độ</div>
      <div class="ic-val">${d.latitude || unknown}</div>
    </div>
    <div class="ip-info-cell">
      <div class="ic-label">Kinh Độ</div>
      <div class="ic-val">${d.longitude || unknown}</div>
    </div>
  `;

  if(d.latitude && d.longitude) {
    mapDiv.innerHTML = `<a href="https://www.google.com/maps?q=${d.latitude},${d.longitude}" target="_blank"
      style="display:inline-flex;align-items:center;gap:7px;color:var(--purple);text-decoration:none;font-weight:700;
      font-size:0.82rem;border:1px solid rgba(168,85,247,0.3);padding:7px 14px;border-radius:9px;transition:0.2s;"
      onmouseover="this.style.background='rgba(168,85,247,0.08)'" onmouseout="this.style.background='transparent'">
      <i class="fa-solid fa-map-location-dot"></i> Xem vị trí trên Google Maps
    </a>`;
  } else {
    mapDiv.innerHTML = '';
  }
}

function doCheckIP() {
  const ip = document.getElementById('ipInput').value.trim();
  if(!ip) { alert('Vui lòng nhập địa chỉ IP!'); return; }
  const resBox = document.getElementById('ipScanResult');
  resBox.style.display = 'block';
  document.getElementById('ipInfoGrid').innerHTML = `<div class="ip-info-cell full-width"><div style="display:flex;align-items:center;gap:8px;color:var(--muted);font-size:0.82rem;"><div class="spinner spinner-sm" style="width:16px;height:16px;border-width:2px;margin-left:0;margin-right:4px;"></div>Đang tra cứu IP: <strong style="color:var(--blue);">${ip}</strong>...</div></div>`;
  document.getElementById('ipMapLink').innerHTML = '';
  fetch(`https://get.geojs.io/v1/ip/geo/${encodeURIComponent(ip)}.json`)
  .then(r=>r.json()).then(d=>{ renderIPResult(d); })
  .catch(()=>{
    document.getElementById('ipInfoGrid').innerHTML = `<div class="ip-info-cell full-width" style="color:var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i> Không thể tra cứu IP này. Kiểm tra lại địa chỉ IP hoặc kết nối mạng.</div>`;
  });
}

function checkMyIP() {
  const resBox = document.getElementById('ipScanResult');
  resBox.style.display = 'block';
  document.getElementById('ipInfoGrid').innerHTML = `<div class="ip-info-cell full-width"><div style="display:flex;align-items:center;gap:8px;color:var(--muted);font-size:0.82rem;"><div class="spinner spinner-sm" style="width:16px;height:16px;border-width:2px;margin-left:0;margin-right:4px;"></div>Đang quét IP của bạn...</div></div>`;
  document.getElementById('ipMapLink').innerHTML = '';
  fetch('https://get.geojs.io/v1/ip/geo.json')
  .then(r=>r.json()).then(d=>{
    document.getElementById('ipInput').value = d.ip || '';
    renderIPResult(d);
  })
  .catch(()=>{
    document.getElementById('ipInfoGrid').innerHTML = `<div class="ip-info-cell full-width" style="color:var(--danger);"><i class="fa-solid fa-shield-halved"></i> Tường lửa chặn quét IP. Thử lại sau.</div>`;
  });
}

// ---- DEVICE REVIEW ----
function loadDeviceRequests() {
  const el = document.getElementById('deviceReqList');
  if(!el) return;
  el.innerHTML = '<div style="color:var(--muted);font-size:0.83rem;text-align:center;padding:18px 0;"><div class="spinner" style="margin:0 auto 10px;width:24px;height:24px;border-width:2px;"></div>Đang tải...</div>';
  fetch('/api/list_device_requests')
  .then(r=>r.json()).then(data=>{
    const badge = document.getElementById('devReqBadge');
    if(data.length > 0) { if(badge){badge.innerText=data.length; badge.style.display='inline';} }
    else { if(badge) badge.style.display='none'; }
    if(!data.length) {
      el.innerHTML = '<div class="dev-empty"><i class="fa-solid fa-inbox"></i>Không có yêu cầu nào đang chờ duyệt</div>';
      return;
    }
    let html = '';
    data.forEach(r => {
      const did = r.device_id || '—';
      const short = did.length > 22 ? did.substring(0,22)+'...' : did;
      html += `<div class="dev-req-card">
        <div class="dev-req-device"><i class="fa-solid fa-fingerprint" style="color:var(--purple);flex-shrink:0;margin-top:2px;"></i>${short}</div>
        <div class="dev-req-meta">
          <span><i class="fa-regular fa-clock"></i> ${r.submitted_at_str}</span>
          <span><i class="fa-solid fa-hourglass-half"></i> Yêu cầu: ${r.val} ${r.unit}</span>
          <span><i class="fa-solid fa-globe"></i> ${r.ip}</span>
          ${r.note ? '<span><i class="fa-solid fa-note-sticky"></i> '+r.note+'</span>' : ''}
        </div>
        <div class="dev-req-actions">
          <span class="badge-pending"><i class="fa-solid fa-clock"></i> Chờ duyệt</span>
          <button class="btn-sm btn-sm-green" onclick="approveDeviceReq('${r.req_id.replace(/'/g,"\\'")}','${did.replace(/'/g,"\\'")}','${r.val}','${r.unit}')"><i class="fa-solid fa-check"></i> Duyệt</button>
          <button class="btn-sm btn-sm-red" onclick="rejectDeviceReq('${r.req_id.replace(/'/g,"\\'")}')"><i class="fa-solid fa-xmark"></i> Từ chối</button>
          <button class="btn-sm btn-sm-blue" onclick="copyText('${did.replace(/'/g,"\\'")}', this)" style="font-size:0.68rem;"><i class="fa-solid fa-copy"></i></button>
        </div>
      </div>`;
    });
    el.innerHTML = html;
  }).catch(()=>{ el.innerHTML = '<div class="dev-empty" style="color:var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i>Lỗi tải dữ liệu</div>'; });
}

function approveDeviceReq(reqId, deviceId, defVal, defUnit) {
  const units = ['phút','tiếng','ngày','tháng','năm','permanent'];
  const unitNames = {'phút':'Phút','tiếng':'Tiếng','ngày':'Ngày','tháng':'Tháng','năm':'Năm','permanent':'Vĩnh viễn'};
  const unitOptions = units.map(u=>`<option value="${u}" ${u===defUnit?'selected':''}>${unitNames[u]||u}</option>`).join('');
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(3,6,12,0.92);z-index:9999;display:flex;justify-content:center;align-items:center;backdrop-filter:blur(12px);';
  modal.innerHTML = `<div style="background:rgba(10,16,28,0.98);border:1px solid rgba(0,200,255,0.35);border-radius:20px;padding:28px 24px;width:min(360px,92vw);box-shadow:0 0 60px rgba(0,200,255,0.15);">
    <div style="font-family:'Orbitron',sans-serif;font-size:0.95rem;font-weight:900;color:var(--blue);margin-bottom:16px;text-align:center;"><i class="fa-solid fa-shield-check"></i> Duyệt Thiết Bị</div>
    <div style="font-size:0.75rem;color:var(--muted);margin-bottom:4px;text-transform:uppercase;font-weight:700;">Device ID</div>
    <div style="font-family:'Orbitron',sans-serif;font-size:0.72rem;color:var(--text);background:rgba(0,0,0,0.4);padding:9px 12px;border-radius:9px;word-break:break-all;margin-bottom:14px;border:1px solid rgba(255,255,255,0.06);">${deviceId}</div>
    <div style="display:flex;gap:10px;margin-bottom:14px;">
      <div style="flex:1;"><div style="font-size:0.73rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:6px;">Thời lượng</div>
        <input type="number" id="apvVal" value="${defVal||1}" min="1" style="width:100%;padding:10px 12px;background:rgba(4,8,16,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:9px;color:var(--text);font-size:0.88rem;outline:none;"></div>
      <div style="flex:1;"><div style="font-size:0.73rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:6px;">Đơn vị</div>
        <select id="apvUnit" style="width:100%;padding:10px 12px;background:rgba(4,8,16,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:9px;color:var(--text);font-size:0.88rem;outline:none;">${unitOptions}</select></div>
    </div>
    <div style="display:flex;gap:8px;">
      <button onclick="this.closest('div[style*=fixed]').remove()" style="flex:1;padding:12px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:var(--muted);font-weight:700;cursor:pointer;font-size:0.85rem;font-family:'Inter',sans-serif;">Hủy</button>
      <button onclick="doApproveDeviceReq('${reqId.replace(/'/g,"\\'")}','${deviceId.replace(/'/g,"\\'")}',document.getElementById('apvVal').value,document.getElementById('apvUnit').value,this.closest('div[style*=fixed]'))" style="flex:2;padding:12px;background:linear-gradient(135deg,#10d98a,#00c8ff);border:none;border-radius:10px;color:#000;font-weight:900;cursor:pointer;font-size:0.85rem;font-family:'Inter',sans-serif;"><i class="fa-solid fa-check-circle"></i> XÁC NHẬN DUYỆT</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
}

function doApproveDeviceReq(reqId, deviceId, val, unit, modalEl) {
  fetch('/api/approve_device_request',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`req_id=${encodeURIComponent(reqId)}&val=${val}&unit=${encodeURIComponent(unit)}`})
  .then(r=>r.json()).then(d=>{
    if(modalEl) modalEl.remove();
    if(d.status==='success'){ loadDeviceRequests(); loadApprovedDevices(); }
    else { alert('Lỗi: '+(d.msg||'Không duyệt được!')); }
  });
}

function rejectDeviceReq(reqId) {
  if(!confirm('Từ chối yêu cầu này?')) return;
  fetch('/api/reject_device_request',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`req_id=${encodeURIComponent(reqId)}`})
  .then(r=>r.json()).then(()=>{ loadDeviceRequests(); });
}

function loadApprovedDevices() {
  const el = document.getElementById('approvedDevList');
  if(!el) return;
  el.innerHTML = '<div style="color:var(--muted);font-size:0.83rem;text-align:center;padding:18px 0;"><div class="spinner" style="margin:0 auto 10px;width:24px;height:24px;border-width:2px;"></div>Đang tải...</div>';
  fetch('/api/list_approved_devices')
  .then(r=>r.json()).then(data=>{
    if(!data.length) {
      el.innerHTML = '<div class="dev-empty"><i class="fa-solid fa-check-double"></i>Chưa có thiết bị nào được duyệt</div>';
      return;
    }
    let html = '';
    data.forEach(d => {
      const did = d.device_id || '—';
      const short = did.length > 22 ? did.substring(0,22)+'...' : did;
      const badge = d.is_expired ? '<span class="badge-expired-dev"><i class="fa-solid fa-xmark-circle"></i> Hết hạn</span>' : '<span class="badge-approved-dev"><i class="fa-solid fa-check-circle"></i> Hợp lệ</span>';
      const ipVal = (d.ip && d.ip !== '—') ? d.ip : '';
      const ipHtml = ipVal ? `
        <div style="margin-top:8px;background:rgba(0,200,255,0.04);border:1px solid rgba(0,200,255,0.15);border-radius:9px;padding:9px 12px;">
          <div style="font-size:0.68rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:5px;"><i class="fa-solid fa-globe" style="color:var(--blue);margin-right:4px;"></i>Địa Chỉ IP & Vị Trí</div>
          <div style="font-family:'Orbitron',sans-serif;font-size:0.8rem;color:var(--success);font-weight:900;margin-bottom:4px;">${ipVal}</div>
          <div id="geo-${did.replace(/[^a-zA-Z0-9]/g,'_')}" style="font-size:0.75rem;color:var(--muted);">
            <span style="display:inline-flex;align-items:center;gap:5px;"><span class="spinner" style="width:12px;height:12px;border-width:2px;display:inline-block;"></span> Đang tra cứu vị trí...</span>
          </div>
        </div>` : '';
      html += `<div class="apv-card" id="apv-${did.replace(/[^a-zA-Z0-9]/g,'_')}">
        <div class="apv-device"><i class="fa-solid fa-fingerprint" style="color:var(--success);margin-right:6px;"></i>${short}</div>
        <div class="apv-meta">
          ${badge}
          <span><i class="fa-solid fa-clock"></i> Còn: ${d.time_left}</span>
          <span><i class="fa-solid fa-calendar-check"></i> Duyệt: ${d.approved_at}</span>
          <span><i class="fa-solid fa-calendar-xmark"></i> Hết hạn: ${d.expiry_str}</span>
        </div>
        ${ipHtml}
        <div class="apv-actions" style="margin-top:9px;">
          <button class="btn-sm btn-sm-blue" onclick="copyText('${did.replace(/'/g,"\\'")}', this)" title="Copy Device ID"><i class="fa-solid fa-copy"></i></button>
          <button class="btn-sm btn-sm-green" onclick="extendApprovedDevice('${did.replace(/'/g,"\\'")}')"><i class="fa-solid fa-calendar-plus"></i> Gia hạn</button>
          <button class="btn-sm btn-sm-red" onclick="deleteApprovedDevice('${did.replace(/'/g,"\\'")}')"><i class="fa-solid fa-trash"></i> Xóa</button>
        </div>
      </div>`;
    });
    el.innerHTML = html;
    // Fetch geo info for each device that has an IP
    data.forEach(d => {
      if(d.ip && d.ip !== '—') {
        const geoKey = d.ip;
        const elId = 'geo-' + d.device_id.replace(/[^a-zA-Z0-9]/g,'_');
        fetchGeoForApprovedDev(geoKey, elId);
      }
    });
  }).catch(()=>{ el.innerHTML = '<div class="dev-empty" style="color:var(--danger);"><i class="fa-solid fa-triangle-exclamation"></i>Lỗi tải dữ liệu</div>'; });
}

const _geoCache = {};
function fetchGeoForApprovedDev(ip, elId) {
  if(_geoCache[ip]) {
    renderGeoInEl(elId, ip, _geoCache[ip]);
    return;
  }
  fetch('https://get.geojs.io/v1/ip/geo/' + encodeURIComponent(ip) + '.json')
  .then(r=>r.json()).then(geo=>{
    _geoCache[ip] = geo;
    renderGeoInEl(elId, ip, geo);
  }).catch(()=>{
    const el = document.getElementById(elId);
    if(el) el.innerHTML = '<span style="color:var(--danger);font-size:0.73rem;"><i class="fa-solid fa-triangle-exclamation"></i> Không tra cứu được vị trí</span>';
  });
}

function renderGeoInEl(elId, ip, geo) {
  const el = document.getElementById(elId);
  if(!el) return;
  const countryMapLocal = {
    'Vietnam':'Việt Nam','United States':'Hoa Kỳ','China':'Trung Quốc','Japan':'Nhật Bản',
    'South Korea':'Hàn Quốc','Singapore':'Singapore','Thailand':'Thái Lan',
    'Germany':'Đức','France':'Pháp','United Kingdom':'Anh','Australia':'Úc',
    'Canada':'Canada','Russia':'Nga','India':'Ấn Độ','Brazil':'Brazil',
    'Indonesia':'Indonesia','Malaysia':'Malaysia','Philippines':'Philippines',
    'Taiwan':'Đài Loan','Hong Kong':'Hồng Kông'
  };
  const country = countryMapLocal[geo.country] || geo.country || '—';
  const city = geo.city || '—';
  const org = geo.organization_name || geo.org || '—';
  const lat = geo.latitude || '';
  const lng = geo.longitude || '';
  const mapLink = (lat && lng) ? `<a href="https://www.google.com/maps?q=${lat},${lng}" target="_blank" style="display:inline-flex;align-items:center;gap:4px;color:var(--purple);text-decoration:none;font-weight:700;font-size:0.73rem;border:1px solid rgba(168,85,247,0.25);padding:3px 9px;border-radius:6px;margin-top:5px;"><i class="fa-solid fa-map-location-dot"></i> Xem bản đồ</a>` : '';
  el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:0.73rem;">
      <div><span style="color:var(--muted);">Quốc gia:</span> <strong style="color:var(--text);">${country}</strong></div>
      <div><span style="color:var(--muted);">Thành phố:</span> <strong style="color:var(--text);">${city}</strong></div>
      <div style="grid-column:1/-1;"><span style="color:var(--muted);">Nhà mạng:</span> <strong style="color:var(--blue);">${org}</strong></div>
    </div>
    ${mapLink}
  `;
}

// ---- ADMIN DIRECT ADD ID ----
function doAdminAddID(e) {
  e.preventDefault();
  const did = document.getElementById('adminDeviceId').value.trim();
  const val = document.getElementById('adminDevVal').value.trim();
  const unit = document.getElementById('adminDevUnit').value;
  const alertEl = document.getElementById('adminAddIDAlert');
  const btn = document.getElementById('adminAddIDBtn');
  if(!did) {
    alertEl.style.cssText='display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
    alertEl.innerHTML='<i class="fa-solid fa-triangle-exclamation"></i> Vui lòng nhập Device ID!';
    return;
  }
  if(unit !== 'permanent' && (!val || isNaN(parseInt(val)) || parseInt(val) < 1)) {
    alertEl.style.cssText='display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
    alertEl.innerHTML='<i class="fa-solid fa-triangle-exclamation"></i> Vui lòng nhập thời gian hợp lệ!';
    return;
  }
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;border-color:rgba(0,0,0,0.2);border-top-color:#000;"></div> Đang xử lý...';
  alertEl.style.display = 'none';
  fetch('/api/add_device_id', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:`device_id=${encodeURIComponent(did)}&val=${encodeURIComponent(val)}&unit=${encodeURIComponent(unit)}`})
  .then(r=>r.json()).then(d=>{
    if(d.status === 'success') {
      alertEl.style.cssText='display:block;background:rgba(16,217,138,0.1);border:1px solid rgba(16,217,138,0.3);color:var(--success);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
      alertEl.innerHTML='<i class="fa-solid fa-circle-check"></i> Đã duyệt & kích hoạt thành công! Device ID hiện đã ở danh sách Đã Duyệt.';
      document.getElementById('adminDeviceId').value = '';
      document.getElementById('adminDevVal').value = '7';
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-circle-plus"></i> DUYỆT & KÍCH HOẠT NGAY';
      setTimeout(()=>{ alertEl.style.display='none'; }, 4000);
      loadApprovedDevices();
    } else {
      alertEl.style.cssText='display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
      alertEl.innerHTML='<i class="fa-solid fa-triangle-exclamation"></i> ' + (d.msg || 'Lỗi hệ thống!');
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-circle-plus"></i> DUYỆT & KÍCH HOẠT NGAY';
    }
  }).catch(()=>{
    alertEl.style.cssText='display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
    alertEl.innerHTML='<i class="fa-solid fa-triangle-exclamation"></i> Lỗi kết nối máy chủ!';
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-circle-plus"></i> DUYỆT & KÍCH HOẠT NGAY';
  });
}

// ---- ADMIN IP LOOKUP ----
function adminLookupIPInfo() {
  const val = document.getElementById('adminLookupIP').value.trim();
  const res = document.getElementById('adminIPLookupResult');
  if(!val) { alert('Vui lòng nhập IP cần tra cứu!'); return; }
  res.style.display = 'block';
  res.innerHTML = '<div style="display:flex;align-items:center;gap:8px;color:var(--muted);font-size:0.8rem;"><div class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;"></div> Đang tra cứu...</div>';
  fetch('https://get.geojs.io/v1/ip/geo/' + encodeURIComponent(val) + '.json')
  .then(r=>r.json()).then(geo=>{
    const countryMapLocal = {
      'Vietnam':'Việt Nam','United States':'Hoa Kỳ','China':'Trung Quốc','Japan':'Nhật Bản',
      'South Korea':'Hàn Quốc','Singapore':'Singapore','Thailand':'Thái Lan',
      'Germany':'Đức','France':'Pháp','United Kingdom':'Anh','Australia':'Úc',
      'Canada':'Canada','Russia':'Nga','India':'Ấn Độ','Brazil':'Brazil',
      'Indonesia':'Indonesia','Malaysia':'Malaysia','Philippines':'Philippines',
      'Taiwan':'Đài Loan','Hong Kong':'Hồng Kông'
    };
    const country = countryMapLocal[geo.country] || geo.country || '—';
    const city = geo.city || '—';
    const org = geo.organization_name || geo.org || '—';
    const lat = geo.latitude || '', lng = geo.longitude || '';
    const mapLink = (lat && lng) ? `<a href="https://www.google.com/maps?q=${lat},${lng}" target="_blank" style="display:inline-flex;align-items:center;gap:5px;color:var(--purple);text-decoration:none;font-weight:700;font-size:0.78rem;border:1px solid rgba(168,85,247,0.25);padding:5px 12px;border-radius:8px;margin-top:8px;"><i class="fa-solid fa-map-location-dot"></i> Xem bản đồ Google Maps</a>` : '';
    res.innerHTML = `
      <div style="background:rgba(0,200,255,0.04);border:1px solid rgba(0,200,255,0.18);border-radius:11px;padding:12px 14px;font-size:0.82rem;">
        <div style="font-family:'Orbitron',sans-serif;font-size:0.88rem;color:var(--success);font-weight:900;margin-bottom:10px;">${geo.ip || val}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:7px;">
          <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Quốc Gia</div><div style="font-size:0.82rem;font-weight:800;">${country}</div></div>
          <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Thành Phố</div><div style="font-size:0.82rem;font-weight:800;">${city}</div></div>
          <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Múi Giờ</div><div style="font-size:0.82rem;font-weight:800;">${geo.timezone || '—'}</div></div>
          <div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Khu Vực</div><div style="font-size:0.82rem;font-weight:800;">${geo.region || geo.timezone_region || '—'}</div></div>
          <div style="grid-column:1/-1;background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Nhà Mạng / Tổ Chức</div><div style="font-size:0.82rem;font-weight:800;color:var(--blue);">${org}</div></div>
          ${lat && lng ? `<div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Vĩ Độ</div><div style="font-size:0.82rem;font-weight:800;">${lat}</div></div><div style="background:rgba(0,0,0,0.3);border-radius:8px;padding:8px 10px;"><div style="font-size:0.65rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:3px;">Kinh Độ</div><div style="font-size:0.82rem;font-weight:800;">${lng}</div></div>` : ''}
        </div>
        ${mapLink}
      </div>`;
  }).catch(()=>{
    res.innerHTML = '<div style="color:var(--danger);font-size:0.8rem;padding:8px;"><i class="fa-solid fa-triangle-exclamation"></i> Không thể tra cứu IP này.</div>';
  });
}

function deleteApprovedDevice(deviceId) {
  if(!confirm('Xóa thiết bị đã duyệt: '+deviceId+'?')) return;
  fetch('/api/delete_approved_device',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`device_id=${encodeURIComponent(deviceId)}`})
  .then(r=>r.json()).then(()=>{ loadApprovedDevices(); });
}

function extendApprovedDevice(deviceId) {
  const units = ['phút','tiếng','ngày','tháng','năm'];
  const unitNames = {'phút':'Phút','tiếng':'Tiếng','ngày':'Ngày','tháng':'Tháng','năm':'Năm'};
  const unitOptions = units.map(u=>`<option value="${u}" ${u==='ngày'?'selected':''}>${unitNames[u]}</option>`).join('');
  const modal = document.createElement('div');
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(3,6,12,0.92);z-index:9999;display:flex;justify-content:center;align-items:center;backdrop-filter:blur(12px);';
  modal.innerHTML = `<div style="background:rgba(10,16,28,0.98);border:1px solid rgba(16,217,138,0.3);border-radius:20px;padding:28px 24px;width:min(340px,92vw);box-shadow:0 0 60px rgba(16,217,138,0.1);">
    <div style="font-family:'Orbitron',sans-serif;font-size:0.9rem;font-weight:900;color:var(--success);margin-bottom:14px;text-align:center;"><i class="fa-solid fa-calendar-plus"></i> Gia Hạn Thiết Bị</div>
    <div style="font-size:0.72rem;color:var(--muted);background:rgba(0,0,0,0.4);padding:8px 12px;border-radius:9px;word-break:break-all;margin-bottom:14px;border:1px solid rgba(255,255,255,0.06);">${deviceId}</div>
    <div style="display:flex;gap:10px;margin-bottom:14px;">
      <div style="flex:1;"><div style="font-size:0.73rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:6px;">Thêm</div>
        <input type="number" id="extVal" value="7" min="1" style="width:100%;padding:10px 12px;background:rgba(4,8,16,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:9px;color:var(--text);font-size:0.88rem;outline:none;"></div>
      <div style="flex:1;"><div style="font-size:0.73rem;color:var(--muted);font-weight:700;text-transform:uppercase;margin-bottom:6px;">Đơn vị</div>
        <select id="extUnit" style="width:100%;padding:10px 12px;background:rgba(4,8,16,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:9px;color:var(--text);font-size:0.88rem;outline:none;">${unitOptions}</select></div>
    </div>
    <div style="display:flex;gap:8px;">
      <button onclick="this.closest('div[style*=fixed]').remove()" style="flex:1;padding:12px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:var(--muted);font-weight:700;cursor:pointer;font-size:0.85rem;font-family:'Inter',sans-serif;">Hủy</button>
      <button onclick="doExtendDevice('${deviceId.replace(/'/g,"\\'")}',document.getElementById('extVal').value,document.getElementById('extUnit').value,this.closest('div[style*=fixed]'))" style="flex:2;padding:12px;background:linear-gradient(135deg,#10d98a,#00c8ff);border:none;border-radius:10px;color:#000;font-weight:900;cursor:pointer;font-size:0.85rem;font-family:'Inter',sans-serif;"><i class="fa-solid fa-plus"></i> GIA HẠN NGAY</button>
    </div>
  </div>`;
  document.body.appendChild(modal);
}

function doExtendDevice(deviceId, val, unit, modalEl) {
  fetch('/api/extend_approved_device',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:`device_id=${encodeURIComponent(deviceId)}&val=${val}&unit=${encodeURIComponent(unit)}`})
  .then(r=>r.json()).then(d=>{
    if(modalEl) modalEl.remove();
    if(d.status==='success'){ loadApprovedDevices(); }
    else { alert('Lỗi: '+(d.msg||'Không gia hạn được!')); }
  });
}

// ---- NETWORK CANVAS ----
(function(){
  const cv=document.getElementById('network-canvas');
  if(!cv) return;
  const ctx=cv.getContext('2d');
  let pts=[];
  function rs(){ cv.width=window.innerWidth; cv.height=window.innerHeight; pts=[]; for(let i=0;i<50;i++) pts.push({x:Math.random()*cv.width,y:Math.random()*cv.height,vx:(Math.random()-0.5)*0.6,vy:(Math.random()-0.5)*0.6}); }
  window.addEventListener('resize',rs); rs();
  function draw(){
    ctx.clearRect(0,0,cv.width,cv.height);
    pts.forEach(p=>{ p.x+=p.vx; p.y+=p.vy; if(p.x<0||p.x>cv.width)p.vx*=-1; if(p.y<0||p.y>cv.height)p.vy*=-1; ctx.beginPath(); ctx.arc(p.x,p.y,1.8,0,Math.PI*2); ctx.fillStyle='rgba(0,200,255,0.55)'; ctx.fill(); });
    for(let i=0;i<pts.length;i++) for(let j=i+1;j<pts.length;j++){
      const dist=Math.hypot(pts[i].x-pts[j].x,pts[i].y-pts[j].y);
      if(dist<110){ ctx.beginPath(); ctx.moveTo(pts[i].x,pts[i].y); ctx.lineTo(pts[j].x,pts[j].y); ctx.strokeStyle=`rgba(0,200,255,${0.07*(1-dist/110)})`; ctx.lineWidth=1; ctx.stroke(); }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();
</script>
</body>
</html>
"""

# ============================================================
#  FREE KEY PAGE  — chỉ hiện key, KHÔNG hiện IP
# ============================================================
FREE_KEY_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Nhận Key Miễn Phí — Xác Thực Bảo Mật</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<!-- ANTI-DDOS: hidden meta refresh trap for bots -->
<meta http-equiv="x-dns-prefetch-control" content="off">
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;500;600;700;800&display=swap');
:root { --bg:#060b14; --blue:#00c8ff; --purple:#a855f7; --grad:linear-gradient(135deg,#00c8ff,#a855f7); --success:#10d98a; --danger:#f43f5e; --warn:#f59e0b; --muted:#6b7a99; --text:#e2e8f0; }
* { box-sizing:border-box; margin:0; padding:0; font-family:'Inter',sans-serif; }
body { background:var(--bg); color:var(--text); min-height:100vh; display:flex; justify-content:center; align-items:center; padding:20px; position:relative; overflow:hidden; }
canvas { position:fixed; inset:0; z-index:0; pointer-events:none; }
.vip-badge { position:fixed; top:14px; right:14px; z-index:10; background:var(--grad); padding:6px 13px; border-radius:20px; font-size:0.7rem; font-weight:800; color:#000; display:flex; align-items:center; gap:5px; text-transform:uppercase; animation:bp 2.5s ease infinite; box-shadow:0 0 18px rgba(0,200,255,0.4); }
@keyframes bp { 0%,100%{box-shadow:0 0 12px rgba(0,200,255,0.35)} 50%{box-shadow:0 0 28px rgba(168,85,247,0.6)} }
.card { background:rgba(10,16,28,0.95); border:1px solid rgba(0,200,255,0.2); border-radius:22px; padding:28px 22px; width:min(440px,100%); text-align:center; box-shadow:0 0 60px rgba(0,200,255,0.1); position:relative; z-index:5; }
@keyframes spin { to{transform:rotate(360deg)} }
.spin-anim { animation:spin 1s linear infinite; }
/* Progress bar */
.prog-wrap { margin:18px 0 6px; }
.prog-outer { background:rgba(255,255,255,0.06); border-radius:100px; height:10px; overflow:hidden; box-shadow:inset 0 0 0 1px rgba(255,255,255,0.05); }
.prog-inner { background:var(--grad); height:100%; border-radius:100px; width:0%; transition:width 0.5s cubic-bezier(.4,0,.2,1); box-shadow:0 0 10px rgba(0,200,255,0.4); }
.prog-pct { font-size:0.78rem; color:var(--blue); font-weight:800; text-align:right; margin-top:6px; font-family:'Orbitron',sans-serif; }
.prog-title { font-size:0.88rem; color:var(--blue); font-weight:800; margin-bottom:4px; }
.prog-sub { font-size:0.75rem; color:var(--muted); margin-bottom:12px; }
/* Security checks */
.checks { display:flex; flex-direction:column; gap:10px; margin-top:16px; text-align:left; }
.chk { display:flex; align-items:center; gap:12px; padding:11px 14px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:13px; transition:all 0.4s; }
.chk-ico { width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:0.9rem; flex-shrink:0; transition:all 0.4s; }
.chk-ico.wait { background:rgba(107,122,153,0.1); border:1px solid rgba(107,122,153,0.25); color:var(--muted); }
.chk-ico.run { background:rgba(0,200,255,0.1); border:1px solid rgba(0,200,255,0.3); color:var(--blue); }
.chk-ico.ok { background:rgba(16,217,138,0.12); border:1px solid rgba(16,217,138,0.35); color:var(--success); }
.chk-ico.fail { background:rgba(244,63,94,0.12); border:1px solid rgba(244,63,94,0.35); color:var(--danger); }
.chk.ok-row { border-color:rgba(16,217,138,0.18); background:rgba(16,217,138,0.04); }
.chk.fail-row { border-color:rgba(244,63,94,0.18); background:rgba(244,63,94,0.04); }
.chk-info { flex:1; }
.chk-name { font-size:0.82rem; font-weight:700; color:var(--text); }
.chk-desc { font-size:0.72rem; color:var(--muted); margin-top:2px; }
/* Result cards */
.res-icon { width:60px; height:60px; background:var(--grad); border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px; font-size:1.5rem; color:#000; box-shadow:0 0 30px rgba(0,200,255,0.4); animation:iconP 2.5s ease infinite; }
@keyframes iconP { 0%,100%{box-shadow:0 0 22px rgba(0,200,255,0.35)} 50%{box-shadow:0 0 40px rgba(168,85,247,0.65)} }
.res-title { font-family:'Orbitron',sans-serif; font-size:1rem; font-weight:900; color:#fff; margin-bottom:20px; }
.key-display { background:rgba(0,0,0,0.7); border:2px dashed rgba(16,217,138,0.4); border-radius:14px; padding:22px 16px; margin:0 0 18px; }
.key-text { font-family:'Orbitron',sans-serif; font-size:1.35rem; font-weight:900; color:var(--success); letter-spacing:2px; word-break:break-all; text-shadow:0 0 20px rgba(16,217,138,0.4); }
.key-sub { font-size:0.75rem; color:var(--muted); margin-top:8px; }
.key-meta { display:flex; justify-content:center; gap:10px; flex-wrap:wrap; margin:10px 0 16px; font-size:0.75rem; color:var(--muted); }
.key-meta span { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:4px 10px; border-radius:20px; display:flex; align-items:center; gap:5px; }
.copy-btn { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; padding:14px; background:var(--grad); border:none; border-radius:12px; font-weight:900; font-size:0.92rem; cursor:pointer; color:#000; text-transform:uppercase; letter-spacing:0.5px; transition:0.2s; }
.copy-btn:hover { transform:translateY(-2px); box-shadow:0 8px 25px rgba(0,200,255,0.35); }
.footer-info { margin-top:20px; font-size:0.78rem; color:var(--muted); line-height:1.8; padding:14px; background:rgba(255,255,255,0.02); border-radius:12px; border:1px solid rgba(255,255,255,0.04); }
.footer-info strong { color:var(--text); }
.err-icon { width:60px; height:60px; background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.3); border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px; font-size:1.5rem; color:var(--danger); }
.err-title { font-family:'Orbitron',sans-serif; font-size:0.9rem; font-weight:900; color:var(--danger); margin-bottom:12px; }
.err-msg { font-size:0.84rem; color:var(--muted); line-height:1.65; margin-bottom:20px; }
.warn-box { background:rgba(245,158,11,0.07); border:1px solid rgba(245,158,11,0.25); border-radius:12px; padding:12px 14px; font-size:0.78rem; color:var(--warn); line-height:1.7; margin-top:14px; }
.retry-btn { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; padding:12px; background:rgba(244,63,94,0.08); border:1px solid rgba(244,63,94,0.25); border-radius:12px; font-weight:800; font-size:0.84rem; cursor:pointer; color:var(--danger); margin-top:12px; transition:0.2s; }
.retry-btn:hover { background:rgba(244,63,94,0.14); }
@keyframes pulse { 0%,100%{opacity:0.4;transform:scale(0.9)} 50%{opacity:1;transform:scale(1.2)} }
.res-icon { width:60px; height:60px; background:var(--grad); border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px; font-size:1.5rem; color:#000; box-shadow:0 0 30px rgba(0,200,255,0.4); animation:iconP 2.5s ease infinite; }
@keyframes iconP { 0%,100%{box-shadow:0 0 22px rgba(0,200,255,0.35)} 50%{box-shadow:0 0 40px rgba(168,85,247,0.65)} }
.res-title { font-family:'Orbitron',sans-serif; font-size:1rem; font-weight:900; color:#fff; margin-bottom:20px; }
.key-display { background:rgba(0,0,0,0.7); border:2px dashed rgba(16,217,138,0.4); border-radius:14px; padding:22px 16px; margin:0 0 18px; }
.key-text { font-family:'Orbitron',sans-serif; font-size:1.35rem; font-weight:900; color:var(--success); letter-spacing:2px; word-break:break-all; text-shadow:0 0 20px rgba(16,217,138,0.4); }
.key-sub { font-size:0.75rem; color:var(--muted); margin-top:8px; }
.key-meta { display:flex; justify-content:center; gap:12px; flex-wrap:wrap; margin:10px 0 16px; font-size:0.76rem; color:var(--muted); }
.key-meta span { background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.06); padding:4px 10px; border-radius:20px; display:flex; align-items:center; gap:5px; }
.copy-btn { display:flex; align-items:center; justify-content:center; gap:8px; width:100%; padding:14px; background:var(--grad); border:none; border-radius:12px; font-weight:900; font-size:0.92rem; cursor:pointer; color:#000; text-transform:uppercase; letter-spacing:0.5px; transition:0.2s; }
.copy-btn:hover { transform:translateY(-2px); box-shadow:0 8px 25px rgba(0,200,255,0.35); }
.footer-info { margin-top:20px; font-size:0.78rem; color:var(--muted); line-height:1.8; padding:14px; background:rgba(255,255,255,0.02); border-radius:12px; border:1px solid rgba(255,255,255,0.04); }
.footer-info strong { color:var(--text); }
.err-icon { width:60px; height:60px; background:rgba(244,63,94,0.15); border:1px solid rgba(244,63,94,0.3); border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 16px; font-size:1.5rem; color:var(--danger); }
.err-title { font-family:'Orbitron',sans-serif; font-size:0.9rem; font-weight:900; color:var(--danger); margin-bottom:12px; }
.err-msg { font-size:0.84rem; color:var(--muted); line-height:1.65; margin-bottom:20px; }
.warn-box { background:rgba(245,158,11,0.07); border:1px solid rgba(245,158,11,0.25); border-radius:12px; padding:12px 14px; font-size:0.78rem; color:var(--warn); line-height:1.7; margin-top:14px; }
</style>
</head>
<body>
<canvas id="fkc"></canvas>
<div class="vip-badge"><i class="fa-solid fa-crown"></i> ADMIN VĂN KHÁNH</div>

<!-- SCAN CARD (progress bar + 3 checks) -->
<div class="card" id="scanBox">
  <div style="font-family:'Orbitron',sans-serif; font-size:1rem; font-weight:900; color:var(--blue); letter-spacing:1px; margin-bottom:4px;">
    <i class="fa-solid fa-shield-halved" style="margin-right:6px;"></i>XÁC THỰC BẢO MẬT
  </div>
  <div class="prog-sub">Hệ thống đang kiểm tra trước khi cấp key miễn phí</div>
  <div class="prog-wrap">
    <div class="prog-outer"><div class="prog-inner" id="progBar"></div></div>
    <div class="prog-pct" id="progPct">0%</div>
  </div>
  <div class="prog-title" id="progLabel">Khởi tạo bảo mật...</div>
  <div class="checks">
    <div class="chk" id="chk1">
      <div class="chk-ico wait" id="chk1ico"><i class="fa-solid fa-circle-dot"></i></div>
      <div class="chk-info">
        <div class="chk-name">Kiểm tra IP thiết bị</div>
        <div class="chk-desc" id="chk1desc">Đang chờ...</div>
      </div>
    </div>
    <div class="chk" id="chk2">
      <div class="chk-ico wait" id="chk2ico"><i class="fa-solid fa-circle-dot"></i></div>
      <div class="chk-info">
        <div class="chk-name">Phát hiện VPN / Proxy</div>
        <div class="chk-desc" id="chk2desc">Đang chờ...</div>
      </div>
    </div>
    <div class="chk" id="chk3">
      <div class="chk-ico wait" id="chk3ico"><i class="fa-solid fa-circle-dot"></i></div>
      <div class="chk-info">
        <div class="chk-name">Xác thực bypass link</div>
        <div class="chk-desc" id="chk3desc">Đang chờ...</div>
      </div>
    </div>
  </div>
</div>

<!-- SUCCESS CARD -->
<div class="card" id="resBox" style="display:none;">
  <div class="res-icon"><i class="fa-solid fa-key"></i></div>
  <div class="res-title">MÃ KEY CỦA BẠN</div>
  <div class="key-display">
    <div class="key-text" id="keyVal">—</div>
    <div class="key-sub">Nhấn nút bên dưới để sao chép key</div>
  </div>
  <div class="key-meta" id="keyMeta">
    <span><i class="fa-solid fa-clock" style="color:var(--blue);"></i> Hạn: 12 giờ</span>
    <span><i class="fa-solid fa-mobile-screen" style="color:var(--purple);"></i> 1 thiết bị</span>
    <span><i class="fa-solid fa-shield-check" style="color:var(--success);"></i> Đã xác thực</span>
  </div>
  <button class="copy-btn" onclick="cpKey()"><i class="fa-solid fa-copy"></i> NHẤN VÀO ĐÂY ĐỂ COPY KEY</button>
  <div class="footer-info">
    <div style="margin-bottom:4px;">Người cấp server: <strong>Văn Khánh VIP</strong></div>
    <div>Hỗ trợ Telegram: <strong style="color:var(--blue);">@vkhanh3010</strong></div>
    <div style="margin-top:8px; font-size:0.72rem; color:rgba(107,122,153,0.7);">Mỗi IP tối đa 3 key/ngày · Không dùng VPN · Key 12 ký tự, hạn 12 giờ.</div>
  </div>
</div>

<!-- ERROR CARD -->
<div class="card" id="errBox" style="display:none;">
  <div class="err-icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
  <div class="err-title">KHÔNG THỂ CẤP KEY</div>
  <div class="err-msg" id="errMsg">Đã xảy ra lỗi.</div>
  <div class="warn-box">
    <i class="fa-solid fa-circle-info"></i> Liên hệ Admin để lấy link mới: <strong style="color:var(--blue);">@vkhanh3010</strong>
  </div>
  <button class="retry-btn" onclick="location.reload()"><i class="fa-solid fa-rotate-right"></i> Thử Lại</button>
</div>

<script>
/* ---- CANVAS BACKGROUND ---- */
(function(){
  const cv=document.getElementById('fkc');
  const ctx=cv.getContext('2d');
  let pts=[];
  function rs(){ cv.width=window.innerWidth; cv.height=window.innerHeight; pts=[]; for(let i=0;i<45;i++) pts.push({x:Math.random()*cv.width,y:Math.random()*cv.height,vx:(Math.random()-0.5)*0.5,vy:(Math.random()-0.5)*0.5}); }
  window.addEventListener('resize',rs); rs();
  function draw(){
    ctx.clearRect(0,0,cv.width,cv.height);
    pts.forEach(p=>{ p.x+=p.vx; p.y+=p.vy; if(p.x<0||p.x>cv.width)p.vx*=-1; if(p.y<0||p.y>cv.height)p.vy*=-1; ctx.beginPath(); ctx.arc(p.x,p.y,1.5,0,Math.PI*2); ctx.fillStyle='rgba(0,200,255,0.4)'; ctx.fill(); });
    for(let i=0;i<pts.length;i++) for(let j=i+1;j<pts.length;j++){
      const dist=Math.hypot(pts[i].x-pts[j].x,pts[i].y-pts[j].y);
      if(dist<110){ ctx.beginPath(); ctx.moveTo(pts[i].x,pts[i].y); ctx.lineTo(pts[j].x,pts[j].y); ctx.strokeStyle='rgba(168,85,247,'+(0.08*(1-dist/110))+')'; ctx.lineWidth=1; ctx.stroke(); }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

/* ---- PROGRESS & CHECK HELPERS ---- */
function setProgress(pct, label) {
  document.getElementById('progBar').style.width = pct + '%';
  document.getElementById('progPct').textContent = pct + '%';
  if(label) document.getElementById('progLabel').textContent = label;
}
function setCheck(n, state, desc) {
  const ico = document.getElementById('chk'+n+'ico');
  const dsc = document.getElementById('chk'+n+'desc');
  const row = document.getElementById('chk'+n);
  ico.className = 'chk-ico ' + state;
  row.className = 'chk' + (state==='ok'?' ok-row':state==='fail'?' fail-row':'');
  if(state==='wait') ico.innerHTML='<i class="fa-solid fa-circle-dot"></i>';
  else if(state==='run') ico.innerHTML='<i class="fa-solid fa-circle-notch spin-anim"></i>';
  else if(state==='ok')  ico.innerHTML='<i class="fa-solid fa-circle-check"></i>';
  else if(state==='fail') ico.innerHTML='<i class="fa-solid fa-circle-xmark"></i>';
  if(desc) dsc.textContent = desc;
}

let generatedKey = null;

function showSuccess(key, han, dev) {
  document.getElementById('scanBox').style.display='none';
  document.getElementById('errBox').style.display='none';
  document.getElementById('resBox').style.display='block';
  document.getElementById('keyVal').innerText = key;
  generatedKey = key;
  if(han||dev){
    document.getElementById('keyMeta').innerHTML =
      (han?`<span><i class="fa-solid fa-clock" style="color:var(--blue);"></i> ${han}</span>`
          :`<span><i class="fa-solid fa-clock" style="color:var(--blue);"></i> 12 giờ</span>`)
      +(dev?`<span><i class="fa-solid fa-mobile-screen" style="color:var(--purple);"></i> ${dev} thiết bị</span>`:'')
      +`<span><i class="fa-solid fa-shield-check" style="color:var(--success);"></i> Đã xác thực</span>`;
  }
}

function showFail(msg, failCheck) {
  setProgress(100, 'Kiểm tra hoàn tất');
  if(failCheck) setCheck(failCheck, 'fail', 'Không đạt yêu cầu');
  setTimeout(()=>{
    document.getElementById('scanBox').style.display='none';
    document.getElementById('resBox').style.display='none';
    document.getElementById('errBox').style.display='block';
    document.getElementById('errMsg').innerHTML = msg;
  }, 700);
}

function cpKey() {
  if(!generatedKey) return;
  navigator.clipboard.writeText(generatedKey)
  .then(()=>{ alert('\\u2705 \\u0110\\u00e3 sao ch\\u00e9p key! D\\u00e1n v\\u00e0o ph\\u1ea7n m\\u1ec1m \\u0111\\u1ec3 s\\u1eed d\\u1ee5ng.'); })
  .catch(()=>{ prompt('Sao ch\\u00e9p th\\u1ee7 c\\u00f4ng:', generatedKey); });
}

/* ---- MAIN SECURITY FLOW ---- */
(function(){
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  if(!token){
    showFail('B\\u1ea1n c\\u1ea7n v\\u01b0\\u1ee3t link r\\u00fat g\\u1ecdn (Link4m) tr\\u01b0\\u1edbc!<br>Li\\u00ean h\\u1ec7 Admin: <strong style="color:var(--blue);">@vkhanh3010</strong>', null);
    return;
  }

  /* Stage 1 — IP scan */
  setProgress(8, 'Đang quét IP thiết bị...');
  setCheck(1,'run','Đang quét IP...');
  let ipDataStr = '';

  fetch('https://get.geojs.io/v1/ip/geo.json')
  .then(r=>r.json())
  .then(d=>{
    if(d && d.ip){
      ipDataStr = 'Client IP: '+d.ip+' | '+(d.city||'')+', '+(d.country||'')+' | Org: '+(d.organization_name||d.org||'N/A');
      setCheck(1,'ok','IP: '+d.ip+' — '+(d.country||'Unknown'));
    } else {
      setCheck(1,'ok','IP đã ghi nhận');
    }
    setProgress(38,'Đang phát hiện VPN/Proxy...');

    /* Stage 2 — VPN indicator */
    setCheck(2,'run','Đang phân tích lưu lượng...');
    setTimeout(()=>{
      setProgress(65,'Đang xác thực bypass link...');
      setCheck(2,'ok','Lưu lượng bình thường');

      /* Stage 3 — server verify */
      setCheck(3,'run','Đang gửi yêu cầu máy chủ...');
      setProgress(82,'Đang tạo key từ máy chủ...');

      fetch('/api/confirm_bypass',{
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:'token='+encodeURIComponent(token)+'&ip_info='+encodeURIComponent(ipDataStr)
      })
      .then(r=>r.json())
      .then(d=>{
        if(d.status==='success'){
          setProgress(100,'Xác thực thành công!');
          setCheck(3,'ok','Bypass hợp lệ — key đã tạo');
          setTimeout(()=>showSuccess(d.key,d.han_dung||null,d.thiet_bi||null),700);
        } else {
          const msg = d.message||'';
          let fc = 3;
          if(msg.includes('VPN')||msg.includes('proxy')||msg.includes('Proxy')) fc=2;
          else if(msg.includes('IP')||msg.includes('thi\\u1ebft b\\u1ecb')||msg.includes('ng\\u00e0y')) fc=1;
          if(fc===1){ setCheck(1,'fail',''); setCheck(2,'ok','OK'); setCheck(3,'ok','OK'); }
          else if(fc===2){ setCheck(2,'fail',''); setCheck(3,'ok','OK'); }
          else { setCheck(3,'fail',''); }
          showFail(msg||'X\\u1ea3y ra l\\u1ed7i kh\\u00f4ng x\\u00e1c \\u0111\\u1ecbnh.', null);
        }
      })
      .catch(()=>{ setCheck(3,'fail','Đứt kết nối'); showFail('L\\u1ed7i k\\u1ebft n\\u1ed1i m\\u00e1y ch\\u1ee7. Th\\u1eed t\\u1ea3i l\\u1ea1i trang!', null); });
    }, 900);
  })
  .catch(()=>{
    setCheck(1,'ok','IP ghi nhận (offline mode)');
    setProgress(65,'Đang xác thực bypass link...');
    setCheck(2,'ok','Bỏ qua (không có mạng ngoài)');
    setCheck(3,'run','Đang kiểm tra server...');
    fetch('/api/confirm_bypass',{
      method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'token='+encodeURIComponent(token)+'&ip_info='
    })
    .then(r=>r.json())
    .then(d=>{
      if(d.status==='success'){
        setProgress(100,'Xác thực thành công!');
        setCheck(3,'ok','OK');
        setTimeout(()=>showSuccess(d.key,d.han_dung||null,d.thiet_bi||null),700);
      } else { setCheck(3,'fail',''); showFail(d.message||'Lỗi xác thực.', null); }
    })
    .catch(()=>{ setCheck(3,'fail',''); showFail('L\\u1ed7i k\\u1ebft n\\u1ed1i m\\u00e1y ch\\u1ee7.', null); });
  });
})();
</script>
</body>
</html>
"""

CHECK_IP_KEY_HTML = """<!DOCTYPE html>
  <html lang="vi">
  <head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
  <title>Check IP Key</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Inter:wght@400;500;600;700;800&display=swap');
  :root{--bg:#050c18;--panel:rgba(8,14,26,0.96);--border:rgba(0,210,255,0.13);--bh:rgba(0,210,255,0.35);--blue:#00d2ff;--purple:#a855f7;--g:linear-gradient(135deg,#00d2ff,#a855f7);--mt:#e2e8f0;--dim:#5a6a8a;--ok:#10d98a;--err:#f43f5e;--warn:#f59e0b;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--bg);color:var(--mt);font-family:'Inter',sans-serif;min-height:100vh;padding-bottom:60px;overflow-x:hidden;}
  canvas#nbg{position:fixed;inset:0;z-index:0;pointer-events:none;}

  /* TOP */
  .topbar{position:fixed;top:0;left:0;right:0;z-index:50;height:56px;background:rgba(5,12,24,0.94);border-bottom:1px solid var(--border);backdrop-filter:blur(18px);display:flex;align-items:center;padding:0 14px;gap:10px;}
  .bk{display:inline-flex;align-items:center;gap:6px;color:var(--blue);font-weight:700;font-size:0.8rem;text-decoration:none;padding:7px 12px;border:1px solid rgba(0,210,255,0.25);border-radius:10px;background:rgba(0,210,255,0.05);transition:all .2s;}
  .bk:hover{background:rgba(0,210,255,0.12);transform:translateX(-2px);}
  .ttl{font-family:'Orbitron',sans-serif;font-size:0.82rem;font-weight:900;background:var(--g);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1.5px;}

  /* WRAP */
  .wrap{width:min(580px,100%);margin:0 auto;padding:74px 14px 0;position:relative;z-index:2;}

  /* HERO */
  .hero{text-align:center;padding:22px 0 18px;}
  .hico{width:66px;height:66px;background:var(--g);border-radius:18px;display:flex;align-items:center;justify-content:center;margin:0 auto 14px;font-size:1.5rem;color:#000;animation:glow 3s ease infinite;}
  @keyframes glow{0%,100%{box-shadow:0 0 22px rgba(0,210,255,.4)}50%{box-shadow:0 0 44px rgba(168,85,247,.6)}}
  .htitle{font-family:'Orbitron',sans-serif;font-size:1.4rem;font-weight:900;background:var(--g);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px;margin-bottom:7px;}
  .hsub{font-size:0.78rem;color:var(--dim);line-height:1.6;}

  /* SEARCH */
  .sc{background:var(--panel);border:1.5px solid var(--bh);border-radius:18px;padding:20px;margin-bottom:16px;backdrop-filter:blur(22px);box-shadow:0 20px 60px rgba(0,0,0,.7);}
  .slbl{font-size:0.69rem;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;}
  .srow{display:flex;gap:9px;}
  .sinp{flex:1;min-width:0;padding:13px 15px;background:rgba(3,7,14,.9);border:1.5px solid rgba(255,255,255,.07);border-radius:12px;color:var(--mt);font-size:0.88rem;font-weight:600;outline:none;font-family:'Inter',sans-serif;transition:.2s;}
  .sinp:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(0,210,255,.09);}
  .sinp::placeholder{color:rgba(90,106,138,.6);}
  .sbtn{flex-shrink:0;padding:13px 18px;background:var(--g);border:none;border-radius:12px;color:#000;font-weight:900;font-size:0.86rem;cursor:pointer;display:flex;align-items:center;gap:6px;transition:.2s;font-family:'Inter',sans-serif;white-space:nowrap;}
  .sbtn:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,210,255,.35);}
  .sbtn:disabled{opacity:.4;cursor:not-allowed;transform:none;box-shadow:none;}

  /* RADAR LOADING */
  .radar-wrap{display:none;background:var(--panel);border:1px solid var(--border);border-radius:18px;padding:36px 20px;text-align:center;margin-bottom:16px;backdrop-filter:blur(20px);}
  .radar-box{position:relative;width:120px;height:120px;margin:0 auto 20px;}
  .radar-ring{position:absolute;border-radius:50%;border:1.5px solid rgba(0,210,255,.22);}
  .rr1{inset:0;}
  .rr2{inset:18px;}
  .rr3{inset:36px;}
  .radar-sweep{position:absolute;inset:0;border-radius:50%;overflow:hidden;}
  .radar-sweep::after{content:'';position:absolute;top:50%;left:50%;width:50%;height:50%;background:conic-gradient(from 0deg,transparent 80%,rgba(0,210,255,.55) 100%);transform-origin:left center;border-radius:0 50px 50px 0;animation:sweep 1.6s linear infinite;}
  @keyframes sweep{to{transform:rotate(360deg)}}
  .radar-dot{position:absolute;width:8px;height:8px;background:var(--blue);border-radius:50%;top:50%;left:50%;transform:translate(-50%,-50%);box-shadow:0 0 10px var(--blue);}
  .radar-outer{position:absolute;inset:0;border-radius:50%;border:2px solid rgba(0,210,255,.45);animation:rpulse 1.6s ease infinite;}
  @keyframes rpulse{0%,100%{transform:scale(1);opacity:.5}50%{transform:scale(1.05);opacity:1}}
  .ld-steps{margin-bottom:0;}
  .ld-step{display:flex;align-items:center;gap:10px;padding:7px 12px;border-radius:10px;background:rgba(0,210,255,.04);border:1px solid transparent;margin-bottom:7px;transition:.3s;text-align:left;}
  .ld-step.active{border-color:rgba(0,210,255,.25);background:rgba(0,210,255,.08);}
  .ld-step.done{border-color:rgba(16,217,138,.22);background:rgba(16,217,138,.05);}
  .ld-step-ic{width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:.7rem;flex-shrink:0;background:rgba(0,210,255,.08);color:var(--dim);transition:.3s;}
  .ld-step.active .ld-step-ic{background:rgba(0,210,255,.15);color:var(--blue);animation:pulse .8s ease infinite;}
  .ld-step.done .ld-step-ic{background:rgba(16,217,138,.12);color:var(--ok);}
  @keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
  .ld-step-txt{font-size:.78rem;font-weight:600;color:var(--dim);transition:.3s;}
  .ld-step.active .ld-step-txt{color:var(--blue);}
  .ld-step.done .ld-step-txt{color:var(--ok);}

  /* ERROR */
  .ebox{background:rgba(244,63,94,.06);border:1px solid rgba(244,63,94,.28);border-radius:16px;padding:20px;display:none;margin-bottom:16px;text-align:center;}
  .eico{font-size:1.8rem;color:var(--err);margin-bottom:8px;}
  .emsg{font-size:.86rem;font-weight:700;color:var(--err);}

  /* RESULTS */
  .results{display:none;}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:16px 18px;margin-bottom:12px;backdrop-filter:blur(18px);box-shadow:0 10px 34px rgba(0,0,0,.5);}
  .card-hd{display:flex;align-items:center;gap:8px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.05);}
  .card-dot{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 9px rgba(16,217,138,.7);animation:glow2 2s ease infinite;flex-shrink:0;}
  @keyframes glow2{0%,100%{box-shadow:0 0 5px rgba(16,217,138,.5)}50%{box-shadow:0 0 14px rgba(16,217,138,.9)}}
  .card-ttl{font-size:.78rem;font-weight:800;color:var(--blue);text-transform:uppercase;letter-spacing:.6px;}

  /* ROWS */
  .drow{display:flex;align-items:flex-start;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04);}
  .drow:last-child{border-bottom:none;padding-bottom:0;}
  .drow:first-child{padding-top:0;}
  .dic{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:.82rem;flex-shrink:0;margin-top:1px;}
  .ic-b{background:rgba(0,210,255,.09);color:var(--blue);}
  .ic-g{background:rgba(16,217,138,.09);color:var(--ok);}
  .ic-p{background:rgba(168,85,247,.09);color:var(--purple);}
  .ic-w{background:rgba(245,158,11,.09);color:var(--warn);}
  .db{flex:1;min-width:0;}
  .dlbl{font-size:.64rem;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:.45px;margin-bottom:3px;}
  .dval{font-size:.86rem;font-weight:700;color:var(--mt);word-break:break-all;line-height:1.5;}
  .dsub{font-size:.72rem;color:var(--dim);margin-top:2px;}
  .cpb{flex-shrink:0;background:rgba(0,210,255,.06);border:1px solid rgba(0,210,255,.18);color:var(--blue);padding:5px 9px;border-radius:7px;font-size:.68rem;font-weight:700;cursor:pointer;transition:.2s;font-family:'Inter',sans-serif;white-space:nowrap;}
  .cpb:hover{background:rgba(0,210,255,.16);}
  .cpb.ok{background:rgba(16,217,138,.09);border-color:rgba(16,217,138,.28);color:var(--ok);}

  /* BADGES */
  .badge{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:20px;font-size:.7rem;font-weight:800;margin-top:5px;}
  .b-act{background:rgba(16,217,138,.1);color:var(--ok);border:1px solid rgba(16,217,138,.25);}
  .b-inact{background:rgba(245,158,11,.1);color:var(--warn);border:1px solid rgba(245,158,11,.25);}
  .b-exp{background:rgba(244,63,94,.1);color:var(--err);border:1px solid rgba(244,63,94,.25);}

  /* GEO GRID */
  .geo-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:4px;}
  .gcell{background:rgba(0,0,0,.3);border-radius:10px;padding:10px 12px;border:1px solid rgba(255,255,255,.04);}
  .gcell.full{grid-column:1/-1;}
  .glbl{font-size:.62rem;color:var(--dim);font-weight:700;text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px;}
  .gval{font-size:.82rem;font-weight:800;color:var(--mt);word-break:break-all;}
  .mlink{display:inline-flex;align-items:center;gap:7px;color:var(--purple);text-decoration:none;font-weight:700;font-size:.78rem;border:1px solid rgba(168,85,247,.28);padding:8px 14px;border-radius:10px;margin-top:11px;transition:.2s;}
  .mlink:hover{background:rgba(168,85,247,.07);}

  /* DEVICE ITEM */
  .devitem{background:rgba(0,0,0,.38);border:1px solid rgba(168,85,247,.16);border-radius:11px;padding:12px 14px;margin-bottom:8px;}
  .devitem:last-child{margin-bottom:0;}
  .devnum{font-size:.68rem;font-weight:700;color:var(--purple);text-transform:uppercase;letter-spacing:.5px;margin-bottom:7px;}
  .devrow{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;font-size:.8rem;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.04);}
  .devrow:last-child{border-bottom:none;padding-bottom:0;}
  .dkey{color:var(--dim);flex-shrink:0;}
  .dval2{color:var(--mt);font-weight:700;text-align:right;word-break:break-all;max-width:65%;}
  </style>
  </head>
  <body>
  <canvas id="nbg"></canvas>

  <div class="topbar">
    <a href="/" class="bk"><i class="fa-solid fa-arrow-left"></i> Quay Lại</a>
    <div class="ttl">CHECK IP KEY</div>
  </div>

  <div class="wrap">
    <!-- HERO -->
    <div class="hero">
      <div class="hico"><i class="fa-solid fa-network-wired"></i></div>
      <div class="htitle">CHECK IP KEY</div>
      <div class="hsub">Tra cứu đầy đủ thông tin key, thiết bị và vị trí địa lý IP</div>
    </div>

    <!-- SEARCH -->
    <div class="sc">
      <div class="slbl"><i class="fa-solid fa-key" style="color:var(--blue);margin-right:5px;"></i>Nhập mã key cần tra cứu</div>
      <div class="srow">
        <input class="sinp" id="inp" placeholder="VD: FREE-ABC12 hoặc 7DAY-XYZ..." onkeydown="if(event.key==='Enter')doCheck()">
        <button class="sbtn" id="sbtn" onclick="doCheck()"><i class="fa-solid fa-magnifying-glass"></i> TRA CỨU</button>
      </div>
    </div>

    <!-- RADAR LOADING -->
    <div class="radar-wrap" id="rdrWrap">
      <div class="radar-box">
        <div class="radar-outer"></div>
        <div class="radar-ring rr1"></div>
        <div class="radar-ring rr2"></div>
        <div class="radar-ring rr3"></div>
        <div class="radar-sweep"></div>
        <div class="radar-dot"></div>
      </div>
      <div class="ld-steps" id="ldSteps">
        <div class="ld-step" id="ls1">
          <div class="ld-step-ic"><i class="fa-solid fa-satellite-dish"></i></div>
          <div class="ld-step-txt">Kết nối tới máy chủ...</div>
        </div>
        <div class="ld-step" id="ls2">
          <div class="ld-step-ic"><i class="fa-solid fa-database"></i></div>
          <div class="ld-step-txt">Truy xuất dữ liệu key...</div>
        </div>
        <div class="ld-step" id="ls3">
          <div class="ld-step-ic"><i class="fa-solid fa-shield-halved"></i></div>
          <div class="ld-step-txt">Phân tích & xác minh thông tin...</div>
        </div>
        <div class="ld-step" id="ls4">
          <div class="ld-step-ic"><i class="fa-solid fa-location-dot"></i></div>
          <div class="ld-step-txt">Định vị địa lý IP...</div>
        </div>
      </div>
    </div>

    <!-- ERROR -->
    <div class="ebox" id="ebox">
      <div class="eico"><i class="fa-solid fa-triangle-exclamation"></i></div>
      <div class="emsg" id="emsg">Key không tồn tại!</div>
    </div>

    <!-- RESULTS -->
    <div class="results" id="results">

      <!-- KEY INFO -->
      <div class="card">
        <div class="card-hd">
          <div class="card-dot"></div>
          <div class="card-ttl">Thông Tin Key</div>
        </div>
        <div class="drow">
          <div class="dic ic-b"><i class="fa-solid fa-key"></i></div>
          <div class="db">
            <div class="dlbl">Mã Key</div>
            <div class="dval" id="r-key" style="font-family:'Orbitron',sans-serif;font-size:.8rem;"></div>
            <div id="r-status-wrap"></div>
          </div>
          <button class="cpb" onclick="cp('r-key',this)"><i class="fa-solid fa-copy"></i> Copy</button>
        </div>
        <div class="drow">
          <div class="dic ic-b"><i class="fa-solid fa-hourglass-half"></i></div>
          <div class="db">
            <div class="dlbl">Thời Hạn Key</div>
            <div class="dval" id="r-dur" style="color:var(--blue);"></div>
          </div>
        </div>
        <div class="drow">
          <div class="dic ic-g"><i class="fa-solid fa-desktop"></i></div>
          <div class="db">
            <div class="dlbl">Địa Chỉ IP Thiết Bị Kích Hoạt</div>
            <div class="dval" id="r-ip" style="color:var(--ok);font-family:'Orbitron',sans-serif;font-size:.78rem;"></div>
            <div class="dsub">IP được ghi nhận lúc kích hoạt key</div>
          </div>
          <button class="cpb" onclick="cp('r-ip',this)"><i class="fa-solid fa-copy"></i> Copy</button>
        </div>
        <div class="drow">
          <div class="dic ic-b"><i class="fa-solid fa-bolt"></i></div>
          <div class="db">
            <div class="dlbl">Thời Gian Kích Hoạt</div>
            <div class="dval" id="r-act"></div>
          </div>
          <button class="cpb" onclick="cp('r-act',this)"><i class="fa-solid fa-copy"></i> Copy</button>
        </div>
        <div class="drow">
          <div class="dic ic-w"><i class="fa-solid fa-calendar-plus"></i></div>
          <div class="db">
            <div class="dlbl">Ngày Tạo Key</div>
            <div class="dval" id="r-created"></div>
          </div>
          <button class="cpb" onclick="cp('r-created',this)"><i class="fa-solid fa-copy"></i> Copy</button>
        </div>
        <div class="drow">
          <div class="dic ic-w"><i class="fa-solid fa-server"></i></div>
          <div class="db">
            <div class="dlbl">Thông Tin Nguồn / Machine</div>
            <div class="dval" id="r-creator" style="font-size:.8rem;line-height:1.6;"></div>
          </div>
          <button class="cpb" onclick="cp('r-creator',this)"><i class="fa-solid fa-copy"></i> Copy</button>
        </div>
      </div>

      <!-- GEO CARD -->
      <div class="card" id="geoCard" style="display:none;">
        <div class="card-hd">
          <div class="dic ic-p" style="width:26px;height:26px;font-size:.72rem;flex-shrink:0;"><i class="fa-solid fa-earth-asia"></i></div>
          <div class="card-ttl">Vị Trí Địa Lý IP</div>
        </div>
        <div class="geo-grid" id="geoGrid">
          <div class="gcell full" style="text-align:center;color:var(--dim);font-size:.8rem;padding:16px;">
            <div style="width:26px;height:26px;border:2px solid rgba(0,210,255,.15);border-top-color:var(--blue);border-radius:50%;animation:sweep 1s linear infinite;margin:0 auto 9px;"></div>
            Đang tra cứu vị trí địa lý...
          </div>
        </div>
        <div id="geoMapWrap"></div>
      </div>

      <!-- DEVICES CARD -->
      <div class="card" id="devCard" style="display:none;">
        <div class="card-hd">
          <div class="dic ic-p" style="width:26px;height:26px;font-size:.72rem;flex-shrink:0;"><i class="fa-solid fa-mobile-screen-button"></i></div>
          <div class="card-ttl">Thiết Bị Đã Đăng Ký</div>
        </div>
        <div id="devList"></div>
      </div>

    </div><!-- end results -->
  </div><!-- end wrap -->

  <script>
  // ---- NETWORK CANVAS BG ----
  (function(){
    var cv=document.getElementById('nbg'),ctx=cv.getContext('2d'),pts=[];
    function rs(){cv.width=innerWidth;cv.height=innerHeight;pts=[];for(var i=0;i<50;i++)pts.push({x:Math.random()*cv.width,y:Math.random()*cv.height,vx:(Math.random()-.5)*.45,vy:(Math.random()-.5)*.45});}
    window.addEventListener('resize',rs);rs();
    function draw(){
      ctx.clearRect(0,0,cv.width,cv.height);
      pts.forEach(function(p){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>cv.width)p.vx*=-1;if(p.y<0||p.y>cv.height)p.vy*=-1;ctx.beginPath();ctx.arc(p.x,p.y,1.5,0,Math.PI*2);ctx.fillStyle='rgba(0,210,255,0.4)';ctx.fill();});
      for(var i=0;i<pts.length;i++)for(var j=i+1;j<pts.length;j++){var d=Math.hypot(pts[i].x-pts[j].x,pts[i].y-pts[j].y);if(d<115){ctx.beginPath();ctx.moveTo(pts[i].x,pts[i].y);ctx.lineTo(pts[j].x,pts[j].y);ctx.strokeStyle='rgba(0,210,255,'+(0.065*(1-d/115))+')';ctx.lineWidth=1;ctx.stroke();}}
      requestAnimationFrame(draw);
    }
    draw();
  })();

  // ---- COPY ----
  function cp(id,btn){
    var val=document.getElementById(id).innerText.trim();
    if(!val||val==='—'||val==='')return;
    navigator.clipboard.writeText(val).then(function(){
      var o=btn.innerHTML;btn.innerHTML='<i class="fa-solid fa-check"></i> Đã copy';btn.classList.add('ok');
      setTimeout(function(){btn.innerHTML=o;btn.classList.remove('ok');},1500);
    }).catch(function(){prompt('Copy:',val);});
  }
  function cpTxt(txt,btn){
    navigator.clipboard.writeText(txt).then(function(){
      var o=btn.innerHTML;btn.innerHTML='<i class="fa-solid fa-check"></i>';btn.classList.add('ok');
      setTimeout(function(){btn.innerHTML=o;btn.classList.remove('ok');},1500);
    }).catch(function(){prompt('Copy:',txt);});
  }

  // ---- RADAR STEPS ----
  var stepTimers=[];
  function clearStepTimers(){stepTimers.forEach(function(t){clearTimeout(t);});stepTimers=[];}
  function setStep(n,state){var el=document.getElementById('ls'+n);if(!el)return;el.className='ld-step '+(state||'');}
  function runSteps(onDone){
    ['ls1','ls2','ls3','ls4'].forEach(function(id){var el=document.getElementById(id);if(el)el.className='ld-step';});
    setStep(1,'active');
    var t1=setTimeout(function(){setStep(1,'done');setStep(2,'active');},700);
    var t2=setTimeout(function(){setStep(2,'done');setStep(3,'active');},1400);
    var t3=setTimeout(function(){setStep(3,'done');setStep(4,'active');},2100);
    var t4=setTimeout(function(){setStep(4,'done');if(onDone)onDone();},2800);
    stepTimers=[t1,t2,t3,t4];
  }

  // ---- COUNTRY MAP ----
  var cmap={'Vietnam':'Viet Nam','United States':'Hoa Ky','China':'Trung Quoc','Japan':'Nhat Ban','South Korea':'Han Quoc','Singapore':'Singapore','Thailand':'Thai Lan','Germany':'Duc','France':'Phap','United Kingdom':'Anh','Australia':'Uc','Canada':'Canada','Russia':'Nga','India':'An Do','Brazil':'Brazil','Indonesia':'Indonesia','Malaysia':'Malaysia','Philippines':'Philippines','Taiwan':'Dai Loan','Hong Kong':'Hong Kong'};
  function xlC(c){return cmap[c]||c||'Khong ro';}

  // ---- GEO RENDER ----
  function renderGeo(ip,geo){
    var uk='Khong ro';
    var country=xlC(geo.country||'');
    var region=geo.region||geo.timezone_region||uk;
    var city=geo.city||uk;
    var org=geo.organization_name||geo.org||uk;
    var tz=geo.timezone||uk;
    var lat=geo.latitude||'';
    var lng=geo.longitude||'';
    var addr=city!==uk?(city+(region!==uk?', '+region:'')+', '+country):uk;

    var h='';
    h+='<div class="gcell full"><div class="glbl">Dia Chi Cu The</div>';
    h+='<div class="gval" style="color:var(--ok);">'+addr+'</div>';
    h+='<button class="cpb" style="margin-top:7px;font-size:.66rem;" onclick="cpTxt(''+addr.replace(/'/g,"\\'")+"',this)"><i class='fa-solid fa-copy'></i> Copy</button></div>";
    h+='<div class="gcell"><div class="glbl">Quoc Gia</div><div class="gval">'+country+'</div></div>';
    h+='<div class="gcell"><div class="glbl">Thanh Pho</div><div class="gval">'+city+'</div></div>';
    h+='<div class="gcell"><div class="glbl">Khu Vuc / Vung</div><div class="gval">'+region+'</div></div>';
    h+='<div class="gcell"><div class="glbl">Mui Gio</div><div class="gval">'+tz+'</div></div>';
    h+='<div class="gcell full"><div class="glbl">Nha Mang / To Chuc</div>';
    h+='<div class="gval" style="color:var(--blue);">'+org+'</div>';
    h+='<button class="cpb" style="margin-top:7px;font-size:.66rem;" onclick="cpTxt(''+org.replace(/'/g,"\\'")+"',this)"><i class='fa-solid fa-copy'></i> Copy</button></div>";
    if(lat&&lng){
      h+='<div class="gcell"><div class="glbl">Vi Do</div><div class="gval">'+lat+'</div></div>';
      h+='<div class="gcell"><div class="glbl">Kinh Do</div><div class="gval">'+lng+'</div></div>';
    }
    document.getElementById('geoGrid').innerHTML=h;

    var mapH=lat&&lng?'<a class="mlink" href="https://www.google.com/maps?q='+lat+','+lng+'" target="_blank"><i class="fa-solid fa-map-location-dot"></i> Xem vi tri tren Google Maps</a>':'';
    document.getElementById('geoMapWrap').innerHTML=mapH;
    document.getElementById('geoCard').style.display='block';
  }

  // ---- MAIN CHECK ----
  function doCheck(){
    var key=document.getElementById('inp').value.trim();
    if(!key){alert('Vui long nhap ma key!');return;}
    var btn=document.getElementById('sbtn');
    btn.disabled=true;
    document.getElementById('rdrWrap').style.display='block';
    document.getElementById('results').style.display='none';
    document.getElementById('ebox').style.display='none';
    document.getElementById('geoCard').style.display='none';
    document.getElementById('devCard').style.display='none';

    clearStepTimers();

    runSteps(function(){
      fetch('/api/get_key_ip_info',{
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:'key='+encodeURIComponent(key)
      })
      .then(function(r){return r.json();})
      .then(function(d){
        document.getElementById('rdrWrap').style.display='none';
        if(!d.exists){
          document.getElementById('emsg').innerHTML='<i class="fa-solid fa-triangle-exclamation"></i> '+(d.msg||'Key khong ton tai!');
          document.getElementById('ebox').style.display='block';
          btn.disabled=false;
          return;
        }

        // Populate key info
        document.getElementById('r-key').innerText=d.key||'—';
        document.getElementById('r-dur').innerText=d.duration||'—';

        var st=d.status||'';
        var scls=st.indexOf('kich hoat')!==-1&&st.indexOf('Chua')===-1?'b-act':(st.indexOf('Chua')!==-1?'b-inact':'b-exp');
        // check Vietnamese properly
        if(st==='Da kich hoat'||st==='Đã kích hoạt')scls='b-act';
        else if(st==='Chua kich hoat'||st==='Chưa kích hoạt')scls='b-inact';
        else scls='b-exp';
        document.getElementById('r-status-wrap').innerHTML='<span class="badge '+scls+'">'+st+'</span>';

        document.getElementById('r-ip').innerText=d.client_ip||'— Chua co thong tin IP —';
        document.getElementById('r-act').innerText=d.activated_time||'—';
        document.getElementById('r-created').innerText=d.created_at||'—';
        document.getElementById('r-creator').innerText=d.creator_info||'—';

        document.getElementById('results').style.display='block';

        // Devices
        var devs=d.devices||[];
        if(devs.length>0){
          var dh='';
          devs.forEach(function(dev,idx){
            var did=dev.device_id||'—';
            var exp=dev.expiry_str||'—';
            var shortId=did.length>22?did.substring(0,22)+'...':did;
            dh+='<div class="devitem">';
            dh+='<div class="devnum"><i class="fa-solid fa-mobile-screen-button"></i> Thiet Bi #'+(idx+1)+'</div>';
            dh+='<div class="devrow"><span class="dkey">Machine ID</span><span class="dval2" title="'+did+'">'+shortId+' <button class="cpb" style="padding:3px 6px;font-size:.62rem;" onclick="cpTxt(''+did.replace(/'/g,"\\'")+"',this)"><i class='fa-solid fa-copy'></i></button></span></div>";
            dh+='<div class="devrow"><span class="dkey">Han su dung</span><span class="dval2">'+exp+'</span></div>';
            dh+='</div>';
          });
          document.getElementById('devList').innerHTML=dh;
          document.getElementById('devCard').style.display='block';
        }

        // Geo lookup
        var ip=d.client_ip;
        if(ip&&ip.length>0&&ip!==''){
          document.getElementById('geoCard').style.display='block';
          fetch('https://get.geojs.io/v1/ip/geo/'+encodeURIComponent(ip)+'.json')
          .then(function(r){return r.json();})
          .then(function(geo){renderGeo(ip,geo);})
          .catch(function(){
            document.getElementById('geoGrid').innerHTML='<div class="gcell full" style="color:var(--err);font-size:.8rem;text-align:center;padding:14px;"><i class="fa-solid fa-shield-halved"></i> Khong the tra cuu vi tri IP.</div>';
          });
        }
        btn.disabled=false;
      })
      .catch(function(){
        document.getElementById('rdrWrap').style.display='none';
        document.getElementById('emsg').innerHTML='<i class="fa-solid fa-plug-circle-xmark"></i> Loi ket noi may chu. Thu lai!';
        document.getElementById('ebox').style.display='block';
        btn.disabled=false;
      });
    });
  }

  // Auto-fill from URL param
  (function(){
    var params=new URLSearchParams(window.location.search);
    var k=params.get('key');
    if(k){document.getElementById('inp').value=k;setTimeout(doCheck,300);}
  })();
  </script>
  </body>
  </html>
  """



DEVICE_REG_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Đăng Ký Thiết Bị</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Inter:wght@400;500;600;700;800&display=swap');
:root { --bg:#060b14; --blue:#00c8ff; --purple:#a855f7; --grad:linear-gradient(135deg,#00c8ff,#a855f7); --success:#10d98a; --danger:#f43f5e; --warn:#f59e0b; --muted:#6b7a99; --text:#e2e8f0; }
* { box-sizing:border-box; margin:0; padding:0; font-family:'Inter',sans-serif; }
body { background:var(--bg); color:var(--text); min-height:100vh; display:flex; justify-content:center; align-items:flex-start; padding:20px 16px 40px; position:relative; overflow-x:hidden; }
canvas { position:fixed; inset:0; z-index:0; pointer-events:none; }
.vip-badge { position:fixed; top:14px; right:14px; z-index:10; background:var(--grad); padding:6px 13px; border-radius:20px; font-size:0.7rem; font-weight:800; color:#000; display:flex; align-items:center; gap:5px; text-transform:uppercase; animation:bp 2.5s ease infinite; box-shadow:0 0 18px rgba(0,200,255,0.4); }
@keyframes bp { 0%,100%{box-shadow:0 0 12px rgba(0,200,255,0.35)} 50%{box-shadow:0 0 28px rgba(168,85,247,0.6)} }
.wrap { width:min(440px,100%); margin:0 auto; padding-top:72px; position:relative; z-index:5; }
.header { text-align:center; margin-bottom:28px; }
.hd-icon { width:66px; height:66px; background:var(--grad); border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 14px; font-size:1.6rem; color:#000; box-shadow:0 0 30px rgba(0,200,255,0.4); animation:iconP 2.5s ease infinite; }
@keyframes iconP { 0%,100%{box-shadow:0 0 22px rgba(0,200,255,0.35)} 50%{box-shadow:0 0 40px rgba(168,85,247,0.65)} }
.hd-title { font-family:'Orbitron',sans-serif; font-size:1.3rem; font-weight:900; background:var(--grad); -webkit-background-clip:text; -webkit-text-fill-color:transparent; letter-spacing:2px; margin-bottom:6px; }
.hd-sub { font-size:0.8rem; color:var(--muted); }
.card { background:rgba(10,16,28,0.95); border:1px solid rgba(0,200,255,0.18); border-radius:20px; padding:24px; margin-bottom:14px; box-shadow:0 20px 60px rgba(0,0,0,0.7); backdrop-filter:blur(24px); }
.fg { margin-bottom:14px; }
.fg label { display:block; font-size:0.72rem; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:7px; }
.fg input, .fg select, .fg textarea { width:100%; padding:12px 14px; background:rgba(4,8,16,0.85); border:1px solid rgba(255,255,255,0.08); border-radius:11px; color:var(--text); font-size:0.88rem; font-weight:500; outline:none; font-family:'Inter',sans-serif; transition:0.2s; }
.fg input:focus, .fg select:focus, .fg textarea:focus { border-color:var(--blue); box-shadow:0 0 0 3px rgba(0,200,255,0.1); }
.fg textarea { resize:none; height:70px; }
.fg select option { background:#0a0e1a; }
.row2 { display:flex; gap:10px; }
.row2 > div { flex:1; }
.btn-sub { width:100%; padding:14px; background:var(--grad); border:none; border-radius:12px; color:#000; font-weight:900; font-size:0.92rem; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:8px; transition:0.2s; letter-spacing:0.4px; margin-top:4px; }
.btn-sub:hover { transform:translateY(-2px); box-shadow:0 8px 28px rgba(0,200,255,0.35); }
.btn-sub:disabled { opacity:0.5; cursor:not-allowed; transform:none; }
.spinner { width:22px; height:22px; border:2px solid rgba(0,200,255,0.15); border-top-color:var(--blue); border-radius:50%; animation:spin 0.75s linear infinite; }
@keyframes spin { to{transform:rotate(360deg)} }
.alert { border-radius:12px; padding:14px 16px; font-size:0.84rem; font-weight:700; display:none; margin-top:12px; }
.alert-success { background:rgba(16,217,138,0.08); border:1px solid rgba(16,217,138,0.3); color:var(--success); }
.alert-error { background:rgba(244,63,94,0.08); border:1px solid rgba(244,63,94,0.3); color:var(--danger); }
.alert-warn { background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.3); color:var(--warn); }
.info-box { background:rgba(0,200,255,0.04); border:1px solid rgba(0,200,255,0.15); border-radius:14px; padding:14px 16px; font-size:0.8rem; color:var(--muted); line-height:1.75; }
.info-box strong { color:var(--text); }
.prog-wrap { margin-top:16px; display:none; }
.prog-track { width:100%; height:8px; background:rgba(255,255,255,0.06); border-radius:99px; overflow:hidden; border:1px solid rgba(0,200,255,0.15); }
.prog-fill { height:100%; width:0%; background:linear-gradient(90deg,#0ff 0%,#00c8ff 35%,#7c3aed 70%,#a855f7 100%); border-radius:99px; transition:width 0.15s linear; box-shadow:0 0 10px rgba(0,200,255,0.5); position:relative; }
.prog-fill::after { content:''; position:absolute; right:0; top:0; bottom:0; width:14px; background:rgba(255,255,255,0.32); border-radius:99px; filter:blur(3px); }
.prog-pct { text-align:center; font-size:0.78rem; font-weight:800; background:var(--grad); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-top:7px; }
</style>
</head>
<body>
<canvas id="drCv"></canvas>
<div class="vip-badge"><i class="fa-solid fa-crown"></i> ADMIN VĂN KHÁNH</div>

<div class="wrap">
  <div class="header">
    <div class="hd-icon"><i class="fa-solid fa-mobile-screen-button"></i></div>
    <div class="hd-title">ĐĂNG KÝ THIẾT BỊ</div>
    <div class="hd-sub">Gửi yêu cầu duyệt Device ID của bạn tới Admin</div>
  </div>

  <div class="card">
    <form id="devRegForm">
      <div class="fg">
        <label><i class="fa-solid fa-fingerprint" style="color:var(--blue);"></i> Device ID / Machine ID</label>
        <input type="text" id="devId" required placeholder="Dán Device ID của thiết bị vào đây...">
      </div>
      <div class="fg">
        <label><i class="fa-solid fa-hourglass-half" style="color:var(--purple);"></i> Thời gian sử dụng mong muốn</label>
        <div class="row2">
          <div>
            <input type="number" id="devVal" value="7" min="1" placeholder="Số lượng">
          </div>
          <div>
            <select id="devUnit">
              <option value="phút">Phút</option>
              <option value="tiếng">Tiếng</option>
              <option value="ngày" selected>Ngày</option>
              <option value="tháng">Tháng</option>
              <option value="năm">Năm</option>
            </select>
          </div>
        </div>
      </div>
      <div class="fg">
        <label><i class="fa-solid fa-note-sticky" style="color:var(--warn);"></i> Ghi chú (tuỳ chọn)</label>
        <textarea id="devNote" placeholder="Lý do xin duyệt, tên thiết bị,..."></textarea>
      </div>
      <div class="prog-wrap" id="progWrap">
        <div class="prog-track"><div class="prog-fill" id="progFill"></div></div>
        <div class="prog-pct" id="progPct">0%</div>
      </div>
      <div class="alert alert-success" id="alertOk"></div>
      <div class="alert alert-error" id="alertErr"></div>
      <div class="alert alert-warn" id="alertWarn"></div>
      <button type="button" class="btn-sub" id="subBtn" onclick="openAddIDModal()"><i class="fa-solid fa-plus-circle"></i> THÊM ID</button>
    </form>
  </div>

  <div class="info-box">
    <div style="font-weight:800;color:var(--blue);margin-bottom:8px;"><i class="fa-solid fa-circle-info"></i> Hướng dẫn</div>
    <div>1. Nhập <strong>Device ID</strong> chính xác của thiết bị bạn muốn duyệt.</div>
    <div>2. Chọn thời gian sử dụng mong muốn.</div>
    <div>3. Nhấn <strong>Gửi Yêu Cầu</strong> và chờ Admin duyệt.</div>
    <div style="margin-top:8px;">Liên hệ Admin: <strong style="color:var(--blue);">@vkhanh3010</strong></div>
  </div>
</div>

<script>
(function(){
  var cv=document.getElementById('drCv');
  if(!cv) return;
  var ctx=cv.getContext('2d'), pts=[];
  function rs(){ cv.width=window.innerWidth; cv.height=window.innerHeight; pts=[]; for(var i=0;i<45;i++) pts.push({x:Math.random()*cv.width,y:Math.random()*cv.height,vx:(Math.random()-0.5)*0.55,vy:(Math.random()-0.5)*0.55}); }
  window.addEventListener('resize',rs); rs();
  function draw(){
    ctx.clearRect(0,0,cv.width,cv.height);
    pts.forEach(p=>{ p.x+=p.vx; p.y+=p.vy; if(p.x<0||p.x>cv.width)p.vx*=-1; if(p.y<0||p.y>cv.height)p.vy*=-1; ctx.beginPath(); ctx.arc(p.x,p.y,1.6,0,Math.PI*2); ctx.fillStyle='rgba(0,200,255,0.45)'; ctx.fill(); });
    for(var i=0;i<pts.length;i++) for(var j=i+1;j<pts.length;j++){
      var dist=Math.hypot(pts[i].x-pts[j].x,pts[i].y-pts[j].y);
      if(dist<105){ ctx.beginPath(); ctx.moveTo(pts[i].x,pts[i].y); ctx.lineTo(pts[j].x,pts[j].y); ctx.strokeStyle='rgba(168,85,247,'+(0.07*(1-dist/105))+')'; ctx.lineWidth=1; ctx.stroke(); }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

var progPf = 0, progTgt = 0, progSi = 0;
var progSteps = [[30,250],[65,300],[90,350],[100,200]];

function startProg() {
  progPf = 0; progTgt = 0; progSi = 0;
  document.getElementById('progWrap').style.display = 'block';
  document.getElementById('progFill').style.width = '0%';
  document.getElementById('progPct').innerText = '0%';
  function nextS(){
    if(progSi >= progSteps.length) return;
    progTgt = progSteps[progSi][0];
    setTimeout(nextS, progSteps[progSi][1]);
    progSi++;
  }
  nextS();
  function tick(){
    if(progPf < progTgt){ progPf = Math.min(progTgt, progPf + 2); }
    var d = Math.min(100, Math.floor(progPf));
    document.getElementById('progFill').style.width = d + '%';
    document.getElementById('progPct').innerText = d + '%';
    if(d < 100){ requestAnimationFrame(tick); }
  }
  requestAnimationFrame(tick);
}

function openDirectActivateModal() { openAddIDModal(); }

function openAddIDModal() {
  var modal = document.createElement('div');
  modal.id = 'directActivateModal';
  modal.style.cssText = 'position:fixed;inset:0;background:rgba(3,6,12,0.93);z-index:9999;display:flex;justify-content:center;align-items:center;backdrop-filter:blur(14px);';
  modal.innerHTML = [
    '<div style="background:rgba(10,16,28,0.99);border:1px solid rgba(0,200,255,0.35);border-radius:22px;padding:30px 26px;width:min(390px,94vw);box-shadow:0 0 60px rgba(0,200,255,0.18);">',
      '<div style="font-family:\'Orbitron\',sans-serif;font-size:1rem;font-weight:900;color:var(--blue);margin-bottom:5px;text-align:center;"><i class="fa-solid fa-plus-circle"></i> THÊM ID THIẾT BỊ</div>',
      '<div style="font-size:0.75rem;color:var(--muted);text-align:center;margin-bottom:20px;">Nhập Device ID, thời gian sử dụng và xác nhận để kích hoạt thiết bị ngay lập tức</div>',
      '<div style="margin-bottom:13px;">',
        '<div style="font-size:0.72rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:7px;"><i class="fa-solid fa-fingerprint" style="color:var(--blue);margin-right:4px;"></i> Device ID / Machine ID</div>',
        '<input type="text" id="daDeviceId" placeholder="Dán Device ID của thiết bị vào đây..." style="width:100%;padding:12px 14px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--text);font-size:0.88rem;outline:none;font-family:\'Inter\',sans-serif;transition:0.2s;" onfocus="this.style.borderColor=\'var(--blue)\'" onblur="this.style.borderColor=\'rgba(255,255,255,0.1)\'">',
      '</div>',
      '<div style="margin-bottom:5px;font-size:0.72rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;"><i class="fa-solid fa-hourglass-half" style="color:var(--purple);margin-right:4px;"></i> Thời Gian Sử Dụng</div>',
      '<div style="display:flex;gap:9px;margin-bottom:13px;">',
        '<input type="number" id="daVal" value="7" min="1" placeholder="Số lượng" style="flex:1;padding:12px 14px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--text);font-size:0.88rem;outline:none;font-family:\'Inter\',sans-serif;transition:0.2s;" onfocus="this.style.borderColor=\'var(--purple)\'" onblur="this.style.borderColor=\'rgba(255,255,255,0.1)\'">',
        '<select id="daUnit" style="flex:1;padding:12px 14px;background:rgba(4,8,16,0.85);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--text);font-size:0.88rem;outline:none;font-family:\'Inter\',sans-serif;transition:0.2s;" onfocus="this.style.borderColor=\'var(--purple)\'" onblur="this.style.borderColor=\'rgba(255,255,255,0.1)\'">',
          '<option value="phút">Phút</option>',
          '<option value="tiếng">Tiếng</option>',
          '<option value="ngày" selected>Ngày</option>',
          '<option value="tháng">Tháng</option>',
          '<option value="năm">Năm</option>',
          '<option value="permanent">Vĩnh viễn</option>',
        '</select>',
      '</div>',
      '<div style="background:rgba(0,200,255,0.04);border:1px solid rgba(0,200,255,0.15);border-radius:10px;padding:10px 13px;font-size:0.78rem;color:var(--muted);margin-bottom:14px;line-height:1.65;">',
        '<i class="fa-solid fa-circle-info" style="color:var(--blue);margin-right:5px;"></i>',
        'Thiết bị sẽ được <strong style="color:var(--success);">duyệt ngay lập tức</strong> và được phép sử dụng dịch vụ sau khi xác nhận.',
      '</div>',
      '<div id="daAlert" style="display:none;border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;"></div>',
      '<div style="display:flex;gap:9px;">',
        '<button onclick="document.getElementById(\'directActivateModal\').remove()" style="flex:1;padding:13px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:11px;color:var(--muted);font-weight:700;cursor:pointer;font-size:0.85rem;font-family:\'Inter\',sans-serif;transition:0.2s;" onmouseover="this.style.background=\'rgba(255,255,255,0.1)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.05)\'">Hủy</button>',
        '<button id="daConfirmBtn" onclick="doDirectActivate()" style="flex:2;padding:13px;background:linear-gradient(135deg,#00c8ff,#a855f7);border:none;border-radius:11px;color:#000;font-weight:900;cursor:pointer;font-size:0.85rem;font-family:\'Inter\',sans-serif;transition:0.2s;letter-spacing:0.3px;"><i class="fa-solid fa-plus-circle"></i> XÁC NHẬN THÊM ID</button>',
      '</div>',
    '</div>'
  ].join('');
  document.body.appendChild(modal);
}

function doDirectActivate() {
  var did = document.getElementById('daDeviceId').value.trim();
  var val = document.getElementById('daVal').value.trim();
  var unit = document.getElementById('daUnit').value.trim();
  var alertEl = document.getElementById('daAlert');
  var btn = document.getElementById('daConfirmBtn');
  if (!did) {
    alertEl.style.cssText = 'display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
    alertEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Vui lòng nhập Device ID!';
    return;
  }
  if (!val || isNaN(parseInt(val)) || parseInt(val) < 1) {
    if (unit !== 'permanent') {
      alertEl.style.cssText = 'display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
      alertEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Vui lòng nhập thời gian sử dụng hợp lệ!';
      return;
    }
  }
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:18px;height:18px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:6px;border-color:rgba(0,0,0,0.2);border-top-color:#000;"></div> Đang xử lý...';
  var body = 'device_id=' + encodeURIComponent(did) + '&val=' + encodeURIComponent(val) + '&unit=' + encodeURIComponent(unit);
  fetch('/api/add_device_id', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: body
  })
  .then(function(r){ return r.json(); })
  .then(function(d){
    if (d.status === 'success') {
      alertEl.style.cssText = 'display:block;background:rgba(16,217,138,0.1);border:1px solid rgba(16,217,138,0.3);color:var(--success);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
      alertEl.innerHTML = '<i class="fa-solid fa-circle-check"></i> Thiết bị đã được kích hoạt thành công! Đang chuyển hướng...';
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-check"></i> ĐÃ THÊM ID';
      setTimeout(function(){ document.getElementById('directActivateModal').remove(); }, 1400);
    } else {
      alertEl.style.cssText = 'display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
      alertEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> ' + (d.msg || 'Kích hoạt thất bại. Thử lại!');
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-plus-circle"></i> XÁC NHẬN THÊM ID';
    }
  })
  .catch(function(){
    alertEl.style.cssText = 'display:block;background:rgba(244,63,94,0.1);border:1px solid rgba(244,63,94,0.3);color:var(--danger);border-radius:10px;padding:10px 13px;font-size:0.82rem;font-weight:700;margin-bottom:12px;';
    alertEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Lỗi kết nối máy chủ. Thử lại sau!';
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-plus-circle"></i> XÁC NHẬN THÊM ID';
  });
}
</script>
</body>
</html>
"""

UI_TEMPLATE = HTML_P1 + HTML_P2 + HTML_P3 + HTML_P5

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(port=port, host='0.0.0.0')
