"""Start the Flask backend + web app:  python run_web.py   ->  http://127.0.0.1:5000"""
from webapp import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["ARENA_ENV"] == "development")
