from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import psycopg2
from uuid import uuid4  # to generate random hash
from datetime import datetime
import os


# Configure Gemini API
genai.configure(api_key="AIzaSyBkGyVajvZctdMiM9ofMKJ4Mj8RitOViio")
model = genai.GenerativeModel("gemini-2.0-flash")

# Flask app setup
app = Flask(__name__)
CORS(app)

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cursor = conn.cursor()

@app.route("/api/home", methods=["GET"])
def home():
    return jsonify({"message": "Hello from backend!"})

@app.route("/api/send", methods=["POST"])
def send_message():
    try:
        data = request.get_json()
        user_message = data.get("message", "")
        cursor = conn.cursor()

        if "add utr" in user_message.lower():
            
            # Ask user for UTR input details
            prompt = f"""The user wants to add a UTR. Ask them for the following details:
            - UTR number
            - Sender's email
            - Receiver's email
            - Amount
            - Date (in YYYY-MM-DD HH:MM:SS format)

            Write the response as a friendly message asking for those details.
            please enter submit utr after providing the details."""

            # Return the response with hash and prompt to provide UTR details
            return jsonify({"reply": prompt}), 200

        elif "submit" in user_message.lower():
            hash_val = uuid4().hex[:14]

            # Ask Gemini to extract data from user message
            prompt = f"""
            Identify and extract the following details from the transaction notification: the UTR number, the sender's email address, the receiver's email address, the transaction amount, and the date and time of the transaction.

            Here is the transaction notification:
            The message is: {user_message}
            Present the extracted information as a JSON object with the keys: "utr", "sender", "receiver", "amount", and "date". Ensure that the "amount" is a numerical value and the "date" includes both the date and the time.

            For example, the output should look like this:

            Example:
            {{
            "utr": "UTR123456789",
            "sender": "sender@example.com",
            "receiver": "receiver@example.com",
            "amount": 1000.50,
            "date": "2024-08-29 03:30:10"
            }}
            don't add json formatting to the output, just return the json object. and don't add any other text.
            Please make sure to extract the information accurately and in the correct format.
            """
            gemini_response = model.generate_content(prompt)
            extracted = gemini_response.text.strip()

            import json
            try:
                utr_data = json.loads(extracted[8:-4])  # Remove the extra characters
            except Exception as json_err:
                return jsonify({"reply": "Failed to extract UTR details from message", "details": extracted}), 400

            try:
                
                cursor.execute("USE utr;")
                conn.commit()
                # Updated SQL to match the SQLite table structure
                cursor.execute("""
                    INSERT INTO transactions (hash, utr, sender, receiver, amount, date)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (
                    hash_val,
                    utr_data["utr"],
                    utr_data["sender"],
                    utr_data["receiver"],
                    float(utr_data["amount"]),
                    utr_data.get("date")  # Use get() to handle missing date
                ))

                conn.commit()
                return jsonify({"reply": f"Transaction added with hash: {hash_val}"}), 200

            except Exception as db_err:
                return jsonify({"reply": str(db_err), "details": str(db_err)}), 500

        elif "show utr" in user_message.lower():
            try:
                # Fetch all UTRs from the database
                cursor.execute("SELECT hash, utr, sender, receiver, amount, date FROM transactions")
                rows = cursor.fetchall()
                # Check if there are any UTRs
                if not rows:
                    reply = "There are no UTRs currently stored."
                else:
                    # Create a dictionary with hash as key instead of a list
                    utr_dict = {}
                    for row in rows:
                        utr_dict[row[0]] = {
                            "utr": row[1],
                            "sender": row[2],
                            "receiver": row[3],
                            "amount": float(row[4]) if row[4] is not None else None,
                            "date": row[5].strftime("%Y-%m-%d %H:%M:%S") if hasattr(row[5], 'strftime') else str(row[5])
                        }
                    
                    # Extract hash from user message if provided
                    import re
                    hash_pattern = re.search(r'([a-fA-F0-9]{14})', user_message)
                    hash_val = hash_pattern.group(1) if hash_pattern else None
                    
                    if hash_val and hash_val in utr_dict:
                        # If user provided a valid hash, show that specific transaction
                        tx_data = utr_dict[hash_val]
                        transaction_info = f"""Transaction details for hash {hash_val}:
        UTR: {tx_data['utr']}
        Sender: {tx_data['sender']}
        Receiver: {tx_data['receiver']}
        Amount: {tx_data['amount']}
        Date: {tx_data['date']}"""
                        
                        # Make the response more conversational using Gemini
                        gemini_prompt = f"""
                        Convert this transaction information into a friendly, conversational response:
                        {transaction_info}
                        
                        Make it sound helpful and natural, as if a person is explaining the transaction details.
                        """
                        gemini_response = model.generate_content(gemini_prompt)
                        reply = gemini_response.text.strip()
                        
                    else:
                        # Otherwise, let the user know what hashes are available
                        available_hashes = list(utr_dict.keys())
                        if len(available_hashes) > 5:
                            hash_display = ", ".join(available_hashes[:5]) + f" and {len(available_hashes) - 5} more"
                        else:
                            hash_display = ", ".join(available_hashes)
                        
                        hash_info = f"I found {len(available_hashes)} transactions. Please provide one of these hash values to see details: {hash_display}"
                        
                        # Make the response more conversational using Gemini
                        gemini_prompt = f"""
                        Convert this information about available transaction hashes into a friendly, conversational response:
                        {hash_info}
                        
                        Make it sound helpful and natural, as if a person is explaining how to view transaction details.
                        """
                        gemini_response = model.generate_content(gemini_prompt)
                        reply = gemini_response.text.strip()
                        
            except Exception as e:
                reply = f"Something went wrong: {str(e)}"
        else:
            prompt = f"""
            The user is looking for information about utr and SwiftTrans. The user message is: {user_message}
            Write the response as a friendly message explaining the information they are looking for. Also provide them with the details of the UTR and SwiftTrans. And give them the option to add UTR or show UTRs.
            """
            response = model.generate_content(prompt)
            reply = response.text.strip()
        # Close the cursor after executing the query
        cursor.close()
        return jsonify({"reply": reply})

    except Exception as e:
        # Make sure the cursor is closed even if an exception occurs
        if 'cursor' in locals() and cursor:
            cursor.close()
        return jsonify({"reply": f"Error: {str(e)}"}), 500
# Run Flask app
if __name__ == "__main__":
    app.run(debug=True, port=8080)
