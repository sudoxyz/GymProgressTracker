# Workout Progress Tracker

A web-based application to track workouts, exercises, and body statistics. Built with Python, Flask, and SQLite, featuring data visualization with Plotly.

## Installation

1.  **Install Dependencies**

    Use pip to install the required packages:

    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration**

    Create a `.env` file in the same directory as `app.py` and add a secret key:

    ```text
    secret_key=your_secret_key_here
    ```

## Usage

1.  **Start the Server**

    Run the application:

    ```bash
    python app.py
    ```

    The database (`database.db`) will be initialized automatically on the first run.

2.  **Access the Application**

    Open your browser and go to: `http://localhost:5000`

3.  **Workflow**
    *   Register a new account.
    *   Add exercises to your list.
    *   Log workouts and body measurements.
    *   View graphs to see your progress over time.
