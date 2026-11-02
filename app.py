from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, io, csv
from functools import wraps
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DB = os.path.join(os.path.dirname(__file__), "users.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL)""")
init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        if not name or not email or len(password)<8:
            flash("Enter your name, a valid email, and a password with at least 8 characters.")
            return render_template("signup.html")
        try:
            with sqlite3.connect(DB) as con:
                cur=con.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                    (name,email,generate_password_hash(password)))
                session["user_id"]=cur.lastrowid
                session["name"]=name
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("That email is already registered. Please sign in.")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        with sqlite3.connect(DB) as con:
            row=con.execute("SELECT id,name,password_hash FROM users WHERE email=?",(email,)).fetchone()
        if row and check_password_hash(row[2],password):
            session["user_id"],session["name"]=row[0],row[1]
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", name=session.get("name","Researcher"))

@app.route("/visualizer")
@login_required
def visualizer():
    return render_template("visualizer.html")

@app.route("/api/chart", methods=["POST"])
@login_required
def chart():
    payload=request.get_json(silent=True) or {}
    palette=payload.get("palette","viridis")
    palette=palette if palette in ["viridis","cividis","coolwarm","RdBu_r","magma","plasma"] else "viridis"
    kind=payload.get("kind","heatmap")
    # Illustrative sample dataset; use upload feature to work with your own CSV.
    rng=np.random.default_rng(21)
    data=np.outer(np.linspace(0.2,1,18),np.linspace(1,0.25,24))
    data += rng.normal(0,0.08,data.shape)
    data=np.clip(data,0,1)
    fig,ax=plt.subplots(figsize=(8.5,4.7),dpi=130)
    if kind=="spatial":
        sns.heatmap(data,cmap=palette,ax=ax,cbar_kws={"label":"Normalized intensity"},xticklabels=False,yticklabels=False)
        ax.set_title("Illustrative spatial intensity map")
    else:
        sns.heatmap(data,cmap=palette,ax=ax,cbar_kws={"label":"Normalized value"},xticklabels=False,yticklabels=False)
        ax.set_title("Illustrative quantitative heatmap")
    ax.set_xlabel("Spatial / feature dimension")
    ax.set_ylabel("Sample / region")
    fig.tight_layout()
    buf=io.BytesIO()
    fig.savefig(buf,format="png",bbox_inches="tight")
    plt.close(fig)
    import base64
    return jsonify(image="data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode())

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f=request.files.get("dataset")
    if not f or not f.filename.lower().endswith(".csv"):
        flash("Please choose a CSV file.")
        return redirect(url_for("visualizer"))
    # Safe, limited CSV parsing for numeric heatmap data.
    try:
        raw=f.stream.read().decode("utf-8-sig")
        rows=list(csv.reader(io.StringIO(raw)))
        if len(rows)<2 or len(rows[0])<2:
            raise ValueError("CSV needs at least two rows and two columns.")
        import pandas as pd
        df=pd.read_csv(io.StringIO(raw))
        numeric=df.select_dtypes(include="number")
        if numeric.shape[0]<2 or numeric.shape[1]<2:
            raise ValueError("Please provide at least two numeric columns and two data rows.")
        numeric=numeric.iloc[:100,:100].fillna(0)
        fig,ax=plt.subplots(figsize=(9,5),dpi=130)
        sns.heatmap(numeric,cmap=request.form.get("palette","cividis"),ax=ax)
        ax.set_title("Your uploaded dataset")
        fig.tight_layout()
        out=os.path.join(UPLOAD_DIR, f"chart_{session['user_id']}.png")
        fig.savefig(out,bbox_inches="tight")
        plt.close(fig)
        session["uploaded_chart"]="/uploaded-chart"
        flash("CSV processed successfully. Your heatmap is ready.")
    except Exception as e:
        flash("Could not process CSV: "+str(e))
    return redirect(url_for("visualizer"))

@app.route("/uploaded-chart")
@login_required
def uploaded_chart():
    from flask import send_file
    path=os.path.join(UPLOAD_DIR,f"chart_{session['user_id']}.png")
    if not os.path.exists(path): return "No uploaded chart found",404
    return send_file(path,mimetype="image/png")

if __name__=="__main__":
    app.run(debug=True)
