from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import psycopg2
from uuid import uuid4  # to generate random hash
from datetime import datetime
import os
from psycopg2 import IntegrityError, errors


app = Flask(__name__)
CORS(app)  # Enable CORS so your React frontend can post to this server

# Create a connection pool or reuse connection more efficiently
def get_db_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# Make sure table exists
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# Initialize the database when the app starts
init_db()

@app.route("/", methods=["POST"])
def receive_form():
    data = request.json
    conn = None
    cursor = None
    
    try:
        # Validate required fields
        if not all(key in data for key in ["fullName", "email", "password"]):
            return jsonify({"error": "Missing required fields"}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute("SELECT email FROM users WHERE email = %s", (data["email"],))
        if cursor.fetchone():
            return jsonify({"error": "Email already exists!"}), 409
            
        # Insert new user
        cursor.execute("""
            INSERT INTO users (full_name, email, password)
            VALUES (%s, %s, %s)
            RETURNING id;
        """, (
            data["fullName"],
            data["email"],
            data["password"],  # Note: In production, you should hash this password!
        ))
        
        # Get the newly created user ID
        user_id = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({
            "message": "User registered successfully!",
            "user_id": user_id
        }), 201

    except psycopg2.errors.UniqueViolation:
        if conn:
            conn.rollback()
        return jsonify({"error": "Email already exists!"}), 409

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error during registration: {str(e)}")
        return jsonify({"error": f"Registration failed: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Add a health check endpoint for debugging
@app.route("/health", methods=["GET"])
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=8081, debug=True)