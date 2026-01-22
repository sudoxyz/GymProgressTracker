import sqlite3
import plotly.io as pio
import datetime
import dotenv
import os
import sys

from waitress import serve
from plotly.graph_objects import Scatter, Figure
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

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

@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = datetime.timedelta(hours=24)

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

    latest_weights = {}
    for workout in workouts:
        if workout['exercise_id'] not in latest_weights:
            latest_weights[workout['exercise_id']] = workout['weight'], workout['reps']

    return body, workouts, exercises, exercise_map, latest_weights

@app.route('/')
@login_required
def index():
    body, workouts, exercises, exercise_map, latest_weights = init_vars()
    return render_template('index.html', body=body, workouts=workouts, exercises=exercises, exercise_map=exercise_map, latest_weights=latest_weights)

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
        flash("Height and weight cannot be empty.", "error")
        return redirect(url_for('index'))
    
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
        flash("Invalid body ID.", "error")
        return redirect(url_for('index'))

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
        flash("Height and weight cannot be empty.", "error")
        return redirect(url_for('index'))
    
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
        flash("Exercise name cannot be empty.", "error")
        return redirect(url_for('index'))
    
    try:
        conn.execute('INSERT INTO exercises (name, user_id) VALUES (?, ?)', (exercise_name, current_user.id))
        conn.commit()
    except sqlite3.IntegrityError:
        flash("Exercise already exists.", "error")
        return redirect(url_for('index'))
    
    conn.close()

    return redirect(url_for('index'))

@app.route('/delete_exercise/<int:exercise_id>')
@login_required
def delete_exercise(exercise_id):
    conn = get_db_connection()

    if not exercise_id:
        flash("Invalid exercise ID.", "error")
        return redirect(url_for('index'))
        
    conn.execute('DELETE FROM workouts WHERE exercise_id = ? AND user_id = ?', (exercise_id, current_user.id))
    conn.execute('DELETE FROM exercises WHERE id = ? AND user_id = ?', (exercise_id, current_user.id))
    
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit_exercise/<int:exercise_id>', methods=['POST'])
@login_required
def edit_exercise(exercise_id):
    new_name = request.form['new_name']

    if not new_name:
        flash("Exercise name cannot be empty.", "error")
        return redirect(url_for('index'))

    conn = get_db_connection()
    conn.execute('UPDATE exercises SET name = ? WHERE id = ? AND user_id = ?', (new_name, exercise_id, current_user.id))

    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_workout', methods=['POST'])
@login_required
def add_workout():
    exercise_id = request.form['exercise_id']
    weight = request.form.get('weight', type=float)
    weight_unit = request.form.get('weight_unit')

    if not weight:
        flash("Please enter weight.", "error")
        return redirect(url_for('index'))

    if weight_unit == 'lb':
        weight = weight * 0.453592

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
    weight = request.form.get('weight', type=float)
    weight_unit = request.form.get('weight_unit')
    reps = request.form['reps']

    if not weight:
        flash("Weight cannot be empty.", "error")
        return redirect(url_for('index'))

    if weight_unit == 'lb':
        weight = weight * 0.453592 

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
        flash("Invalid workout ID.", "error")
        return redirect(url_for('index'))

    conn.execute('DELETE FROM workouts WHERE id = ? AND user_id = ?', (workout_id, current_user.id))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/exercise_graph/<int:exercise_id>')
@login_required
def exercise_graph(exercise_id):
    conn = get_db_connection()

    if not exercise_id:
        flash("Invalid exercise ID.", "error")
        return redirect(url_for('index'))

    exercise = conn.execute('SELECT * FROM exercises WHERE id = ? AND user_id = ?', (exercise_id, current_user.id)).fetchone()

    if not exercise:
        flash("Exercise not found.", "error")
        return redirect(url_for('index'))

    workouts = conn.execute('''
        SELECT * FROM workouts WHERE exercise_id = ? AND user_id = ?
        ORDER BY date DESC
    ''', (exercise_id, current_user.id)).fetchall()

    conn.close()

    dates = [datetime.datetime.strptime(workout['date'], "%Y-%m-%d %H:%M:%S") for workout in workouts]
    weights = [round(workout['weight'], 2) for workout in workouts]
    reps = [workout['reps'] for workout in workouts]

    fig_weights = Figure()
    fig_weights.add_trace(Scatter(x=dates, y=weights, mode='lines+markers', name='', hoverinfo='x+y', hovertemplate='%{x}<br>%{y} kg'))
    fig_weights.update_layout(title={'text': f'Progression in weight used for {exercise["name"]}', 'x': 0.5}, xaxis_title='Date & Time', yaxis_title='Weight (kg)', dragmode='pan')

    fig_reps = Figure()
    fig_reps.add_trace(Scatter(x=dates, y=reps, mode='lines+markers', name='', hoverinfo='x+y', hovertemplate='%{x}<br>%{y} reps'))
    fig_reps.update_layout(title={'text': f'Progression in reps for {exercise["name"]}', 'x': 0.5}, xaxis_title='Date & Time', yaxis_title='Reps', dragmode='pan')

    graph_weights_html = pio.to_html(fig_weights, full_html=False, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': False})
    graph_reps_html = pio.to_html(fig_reps, full_html=False, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': False})

    return render_template('exercise_graph.html', exercise=exercise, graph_weights_html=graph_weights_html, graph_reps_html=graph_reps_html)

@app.route('/graph')
@login_required
def graph():
    conn = get_db_connection()

    body = conn.execute('SELECT * FROM body WHERE user_id = ? ORDER BY date DESC', (current_user.id,)).fetchall()
    conn.close()

    dates = [datetime.datetime.strptime(entry['date'], "%Y-%m-%d %H:%M:%S") for entry in body]
    weights = [entry['weight'] for entry in body]
    heights = [entry['height'] for entry in body]

    fig_weight = Figure()
    fig_weight.add_trace(Scatter(x=dates, y=weights, mode='lines+markers', name='', hoverinfo='x+y', hovertemplate='%{x}<br>%{y} kg'))
    fig_weight.update_layout(title={'text': f'Weight Progression', 'x': 0.5}, xaxis_title='Date & Time', yaxis_title='Weight (kg)', dragmode='pan')
    fig_height = Figure()
    fig_height.add_trace(Scatter(x=dates, y=heights, mode='lines+markers', name='', hoverinfo='x+y', hovertemplate='%{x}<br>%{y} cm'))
    fig_height.update_layout(title={'text': f'Height Progression', 'x': 0.5}, xaxis_title='Date & Time', yaxis_title='Height (cm)', dragmode='pan')

    graph_weight_html = pio.to_html(fig_weight, full_html=False, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': False})
    graph_height_html = pio.to_html(fig_height, full_html=False, config={'responsive': True, 'scrollZoom': True, 'displayModeBar': False})

    return render_template('graph.html', graph_weight_html=graph_weight_html, graph_height_html=graph_height_html)

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
            flash("Invalid username or password", "error")
            return render_template('login.html')
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
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            flash("Username already taken.", "error")
            return render_template('register.html')
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
        flash("Old password is incorrect.", "error")
        return redirect(url_for('index'))
        
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == "__main__":
    init_db()  
    if sys.argv.__contains__('debug'):
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        serve(app, host='0.0.0.0', port=5000)

