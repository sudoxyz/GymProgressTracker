import sqlite3
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import dotenv
import os
import datetime
from waitress import serve

dotenv.load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("secret_key")
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  
    conn.execute("PRAGMA foreign_keys = ON")
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

def init_vars():
    conn = get_db_connection()

    body = conn.execute('SELECT * FROM body WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()
    workouts = conn.execute('SELECT * FROM workouts WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()
    exercises = conn.execute('SELECT * FROM exercises WHERE user_id = ?', (current_user.id,)).fetchall()
    exercise_map = {exercise['id']: exercise['name'] for exercise in exercises}

    conn.close()

    return body, workouts, exercises, exercise_map

@app.route('/')
@login_required
def index():
    body, workouts, exercises, exercise_map = init_vars()
    error = request.args.get('error')
    
    if error:
        return render_template('index.html', body=body, workouts=workouts, exercises=exercises, exercise_map=exercise_map, error=error)
    
    return render_template('index.html', body=body, workouts=workouts, exercises=exercises, exercise_map=exercise_map)

@app.route('/add_body', methods=['POST'])
@login_required
def add_body():
    conn = get_db_connection()

    height = request.form['height']
    weight = request.form['weight']

    if weight != '':
        weight = float(weight)

    oldHeight = conn.execute('SELECT height FROM body WHERE user_id = ? ORDER BY date DESC LIMIT 1', (current_user.id,)).fetchone()
    oldWeight = conn.execute('SELECT weight FROM body WHERE user_id = ? ORDER BY date DESC LIMIT 1', (current_user.id,)).fetchone()

    if not height and not weight:
        return redirect(url_for('index', error="Height and weight cannot be empty. Please provide at least one value."))

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

    if not body_id:
        return redirect(url_for('index', error="Invalid body ID."))

    conn.execute('DELETE FROM body WHERE id = ? AND user_id = ?', (body_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit_body/<int:body_id>', methods=['POST'])
@login_required
def edit_body(body_id):
    conn = get_db_connection()
    height = request.form['height']
    weight = request.form['weight']

    if not height and not weight:
        return redirect(url_for('index', error="Height and weight cannot be empty."))

    conn.execute('UPDATE body SET height = ?, weight = ? WHERE id = ? AND user_id = ?', 
                 (height, weight, body_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_exercise', methods=['POST'])
@login_required
def add_exercise():
    exercise_name = request.form['exercise_name']
    
    conn = get_db_connection()

    if not exercise_name:
        return redirect(url_for('index', error="Exercise name cannot be empty."))
    
    try:
        conn.execute('INSERT INTO exercises (name, user_id) VALUES (?, ?)', (exercise_name, current_user.id))
        conn.commit()
    except sqlite3.IntegrityError:
        return redirect(url_for('index', error="Exercise already exists!"))
    
    conn.close()

    return redirect(url_for('index'))

@app.route('/delete_exercise/<int:exercise_id>')
@login_required
def delete_exercise(exercise_id):
    conn = get_db_connection()

    if not exercise_id:
        return redirect(url_for('index', error="Invalid exercise ID."))
    
    conn.execute('DELETE FROM exercises WHERE id = ? AND user_id = ?', (exercise_id, current_user.id))
    conn.execute('DELETE FROM workouts WHERE exercise_id = ? AND user_id = ?', (exercise_id, current_user.id))

    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit_exercise/<int:exercise_id>', methods=['POST'])
@login_required
def edit_exercise(exercise_id):
    new_name = request.form['new_name']

    if not new_name:
        return redirect(url_for('index', error="Exercise name cannot be empty."))

    conn = get_db_connection()
    conn.execute('UPDATE exercises SET name = ? WHERE id = ? AND user_id = ?', (new_name, exercise_id, current_user.id))

    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_workout', methods=['POST'])
@login_required
def add_workout():
    exercise_id = request.form['exercise_id']
    weight_kg = request.form.get('weight_kg', type=float)
    weight_lb = request.form.get('weight_lb', type=float)

    if not weight_kg and not weight_lb:
        return redirect(url_for('index', error="Please enter weight in either kg or lbs."))

    if weight_lb:
        weight = weight_lb * 0.453592

    elif weight_kg:
        weight = weight_kg

    reps = request.form['reps']

    conn = get_db_connection()
    conn.execute('INSERT INTO workouts (exercise_id, weight, reps, user_id) VALUES (?, ?, ?, ?)', 
                 (exercise_id, weight, reps, current_user.id))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

@app.route('/edit_workout/<int:workout_id>', methods=['POST'])
@login_required
def edit_workout(workout_id):
    conn = get_db_connection()
    weight = request.form['weight']
    reps = request.form['reps']

    if not weight and not reps:
        return redirect(url_for('index', error="Weight and reps cannot be empty."))

    conn.execute('UPDATE workouts SET weight = ?, reps = ? WHERE id = ? AND user_id = ?', 
                 (weight, reps, workout_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete_workout/<int:workout_id>')
@login_required
def delete_workout(workout_id):
    conn = get_db_connection()

    if not workout_id:
        return redirect(url_for('index', error="Invalid workout ID."))

    conn.execute('DELETE FROM workouts WHERE id = ? AND user_id = ?', (workout_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/exercise_graph/<int:exercise_id>')
@login_required
def exercise_graph(exercise_id):
    conn = get_db_connection()

    if not exercise_id:
        return redirect(url_for('index', error="Invalid exercise ID."))

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

    fig_weights, ax_weights = plt.subplots()
    plt.subplots()
    ax_weights.plot(dates, weights, label="Weight Used (kg)", color='g', marker='o', markersize=3)
    ax_weights.set_title(f"Progression in weight used for {exercise['name']}")
    ax_weights.set_xlabel("Date")
    ax_weights.invert_xaxis()
    ax_weights.set_ylabel("Weight")
    ax_weights.legend()

    img_weights = BytesIO()
    fig_weights.savefig(img_weights, format='png')
    img_weights.seek(0)
    img_weights_b64 = base64.b64encode(img_weights.getvalue()).decode('utf-8')

    fig_reps, ax_reps = plt.subplots()
    plt.subplots()
    ax_reps.plot(dates, reps, label="Reps", color='b', marker='o', markersize=3)
    ax_reps.set_title(f"Progression in reps for {exercise['name']}")
    ax_reps.set_xlabel("Date")
    ax_reps.invert_xaxis()
    ax_reps.set_ylabel("Reps")
    ax_reps.legend()

    img_reps = BytesIO()
    fig_reps.savefig(img_reps, format='png')
    img_reps.seek(0)
    img_reps_b64 = base64.b64encode(img_reps.getvalue()).decode('utf-8')

    return render_template('exercise_graph.html', img_weights_b64=img_weights_b64, img_reps_b64=img_reps_b64, exercise=exercise)

@app.route('/graph')
@login_required
def graph():
    conn = get_db_connection()

    body = conn.execute('SELECT * FROM body WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()

    conn.close()

    dates = [stats['date'] for stats in body]
    weights = [stats['weight'] for stats in body]
    heights = [stats['height'] for stats in body]

    fig_weight, ax_weight = plt.subplots()
    ax_weight.plot(dates, weights, label="Weight (kg)", color='b')
    ax_weight.set_title("Weight Progression")
    ax_weight.set_xlabel("Date")
    ax_weight.invert_xaxis()
    ax_weight.set_ylabel("Weight (kg)")
    ax_weight.legend()

    img_weight = BytesIO()
    fig_weight.savefig(img_weight, format='png')
    img_weight.seek(0)
    img_weight_b64 = base64.b64encode(img_weight.getvalue()).decode('utf-8')


    fig_height, ax_height = plt.subplots()
    ax_height.plot(dates, heights, label="Height (cm)", color='g')
    ax_height.set_title("Height Progression")
    ax_height.set_xlabel("Date")
    ax_height.invert_xaxis()
    ax_height.set_ylabel("Height (cm)")
    ax_height.legend()

    img_height = BytesIO()
    fig_height.savefig(img_weight, format='png')
    img_height.seek(0)
    img_height_b64 = base64.b64encode(img_weight.getvalue()).decode('utf-8')

    return render_template('graph.html', img_weight_b64=img_weight_b64, img_height_b64=img_height_b64)

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

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    old_password = request.form['old_password']
    new_password = request.form['new_password']
    
    if check_password_hash(current_user.password, old_password):
        conn = get_db_connection()
        hashed_password = generate_password_hash(new_password)
        conn.execute('UPDATE accounts SET password = ? WHERE id = ?', (hashed_password, current_user.id))
        conn.commit()
        conn.close()
    
    else:
        return redirect(url_for('index', error="Old password is incorrect."))
    
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == "__main__":
    init_db()  
    app.run(debug=True)
    # serve(app, host='0.0.0.0', port=5000)
