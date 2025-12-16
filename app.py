import sqlite3
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import dotenv
import os

dotenv.load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("secret_key")
login_manager = LoginManager()
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM accounts WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if not user:
            return None
        return User(user['id'], user['username'], user['password'])

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  
    return conn

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS exercises (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    user_id INTEGER,
                    UNIQUE(name, user_id),
                    FOREIGN KEY(user_id) REFERENCES accounts(id)
                  )''')

    c.execute('''CREATE TABLE IF NOT EXISTS workouts (
                    id INTEGER PRIMARY KEY,
                    exercise_id INTEGER,
                    weight REAL NOT NULL,
                    reps INTEGER NOT NULL,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER,
                    FOREIGN KEY (exercise_id) REFERENCES exercises(id),
                    FOREIGN KEY(user_id) REFERENCES accounts(id)
                  )''')

    c.execute('''CREATE TABLE IF NOT EXISTS body (
                    id INTEGER PRIMARY KEY,
                    height REAL NOT NULL,
                    weight REAL NOT NULL,
                    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER,
                    FOREIGN KEY(user_id) REFERENCES accounts(id)
                  )''')

    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL
                  )''')

    conn.commit()
    conn.close()

@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    
    body = conn.execute('SELECT * FROM body WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()
    workouts = conn.execute('SELECT * FROM workouts WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()
    exercises = conn.execute('SELECT * FROM exercises WHERE user_id = ?', (current_user.id,)).fetchall()

    conn.close()
    return render_template('index.html', body=body, workouts=workouts, exercises=exercises)

@app.route('/add_body', methods=['POST'])
@login_required
def add_body():
    conn = get_db_connection()

    height = request.form['height']
    weight = float(request.form['weight']) 

    oldHeight = conn.execute('SELECT height FROM body WHERE user_id = ? ORDER BY date DESC LIMIT 1', (current_user.id,)).fetchone()
    oldWeight = conn.execute('SELECT weight FROM body WHERE user_id = ? ORDER BY date DESC LIMIT 1', (current_user.id,)).fetchone()

    if oldHeight and oldWeight:
        print(oldHeight["height"], oldWeight["weight"])

    if not height:
        height = oldHeight["height"] if oldHeight else 0

    if not weight:
        weight = oldWeight["weight"] if oldWeight else 0

    conn = get_db_connection()
    conn.execute('INSERT INTO body (height, weight, user_id) VALUES (?, ?, ?)', (height, weight, current_user.id))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

@app.route('/delete_body/<int:body_id>')
@login_required
def delete_body(body_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM body WHERE id = ? AND user_id = ?', (body_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_exercise', methods=['POST'])
@login_required
def add_exercise():
    exercise_name = request.form['exercise_name']
    
    conn = get_db_connection()
    
    try:
        conn.execute('INSERT INTO exercises (name, user_id) VALUES (?, ?)', (exercise_name, current_user.id))
        conn.commit()
    except sqlite3.IntegrityError:
        return redirect(url_for('index', error="Exercise already exists!"))
    
    conn.close()

    return redirect(url_for('index'))

@app.route('/add_workout', methods=['POST'])
@login_required
def add_workout():
    exercise_id = request.form['exercise_id']
    weight = float(request.form['weight'])
    reps = request.form['reps']

    conn = get_db_connection()
    conn.execute('INSERT INTO workouts (exercise_id, weight, reps, user_id) VALUES (?, ?, ?, ?)', 
                 (exercise_id, weight, reps, current_user.id))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

@app.route('/delete_workout/<int:workout_id>')
@login_required
def delete_workout(workout_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM workouts WHERE id = ? AND user_id = ?', (workout_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/exercise_graph/<int:exercise_id>')
@login_required
def exercise_graph(exercise_id):
    conn = get_db_connection()

    exercise = conn.execute('SELECT * FROM exercises WHERE id = ? AND user_id = ?', (exercise_id, current_user.id)).fetchone()

    if not exercise:
        conn.close()
        return redirect(url_for('index'))

    workouts = conn.execute('''
        SELECT * FROM workouts WHERE exercise_id = ? AND user_id = ?
        ORDER BY date DESC
    ''', (exercise_id, current_user.id)).fetchall()

    conn.close()

    dates = [workout['date'] for workout in workouts]
    weights = [workout['weight'] for workout in workouts]
    reps = [workout['reps'] for workout in workouts]

    fig, ax = plt.subplots()
    ax.plot(dates, weights, label="Weight Used (kg)", color='g')
    ax.plot(dates, reps, label="Reps", color='b')
    ax.set_title(f"Progression for {exercise['name']}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Weight / Reps")
    ax.legend()

    img = BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)
    img_b64 = base64.b64encode(img.getvalue()).decode('utf-8')

    return render_template('exercise_graph.html', img_b64=img_b64, exercise=exercise)

@app.route('/graph')
@login_required
def graph():
    conn = get_db_connection()

    body = conn.execute('SELECT * FROM body WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()

    conn.close()

    dates = [stats['date'] for stats in body]
    weights = [stats['weight'] for stats in body]
    heights = [stats['height'] for stats in body]

    fig, ax = plt.subplots()
    ax.plot(dates, weights, label="Weight (kg)", color='b')
    ax.plot(dates, heights, label="Height (cm)", color='g')
    ax.set_title("Weight and Height Progression")
    ax.set_xlabel("Date")
    ax.set_ylabel("Weight (kg) / Height (cm)")
    ax.legend()

    img = BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)
    img_b64 = base64.b64encode(img.getvalue()).decode('utf-8')

    return render_template('graph.html', img_b64=img_b64)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM accounts WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['password'])
            login_user(user_obj)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO accounts (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('register.html', error="Username already taken")
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == "__main__":
    init_db()  
    login_manager.init_app(app)
    app.run(debug=True)
