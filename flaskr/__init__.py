import os
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

def create_app():
    # 1. Instantiate the Flask application
    app = Flask(__name__, instance_relative_config=True)

    # 2. Basic fallback config
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Main Web Page Route (Renders HTML UI)
    @app.route('/', methods=['GET'])
    def index():
        return render_template('index.html')

    # 3. Health check route (GET / Read)
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "online", "message": "Chatbot service running"}), 200

    # Register blueprints
    from . import db
    db.init_app(app)

    from . import auth
    app.register_blueprint(auth.bp)

    from . import chat
    app.register_blueprint(chat.bp)

    return app