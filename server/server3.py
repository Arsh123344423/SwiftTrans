from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import psycopg2
from uuid import uuid4  # to generate random hash
from datetime import datetime
import os
from psycopg2 import IntegrityError, errors


app = Flask(__name__)

CORS(app, origins=["http://localhost:3001"], supports_credentials=True)

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cursor = conn.cursor()
@app.route("/", methods=["POST"])
def receive_form():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT full_name, email FROM users WHERE email = %s AND password = %s",
            (email, password)
        )
        user = cursor.fetchone()
        cursor.close()

        if user:
            return jsonify({
                "message": "Login successful!",
                "user": {
                    "full_name": user[0],
                    "email": user[1]
                }
            }), 200
        else:
            return jsonify({
                "message": "Invalid email or password"
            }), 401
            
    except Exception as e:
        return jsonify({
            "message": f"Server error: {str(e)}"
        }), 500
if __name__ == "__main__":
    app.run(port=8082, debug=True)
