from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app)  # Allow requests from frontend

sender_email = "events.artiligent@gmail.com"
sender_password = "ulcsqapxxkxslkhh"
smtp_server = "smtp.gmail.com"
port = 465

@app.route("/send-alert", methods=["POST"])
def send_alert():
    data = request.json
    recipient = data.get("email")
    subject = data.get("subject", "Avaya Health Alert")
    body = data.get("body", "This is a system health alert.")

    if not recipient:
        return jsonify({"error": "Email address required"}), 400

    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL(smtp_server, port) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient, msg.as_string())

        return jsonify({"message": f"Alert sent to {recipient}"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
