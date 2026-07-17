   "status": "success",
            "campaign_id": campaign_id,
            "message": f"Campaign created. Message 1 sent to {len(clients)} clients"
        }), 200
    
    except Exception as e:
        conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500

def send_message_1(client, client_id, campaign_id):
    """Send personalized Message 1 via Email, SMS, WhatsApp"""
    message_content = MESSAGE_1.replace("{NAME}", client.get("name", ""))
    
    # Send Email
    send_email(client.get("email"), f"AI automation for {client.get('name')}", message_content)
    
    # Send SMS
    send_sms(client.get("phone"), message_content[:160])
    
    # Send WhatsApp
    send_whatsapp(client.get("phone"), message_content)
    
    # Log messages
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    for channel in ["email", "sms", "whatsapp"]:
        cursor.execute(
            """INSERT INTO messages (client_id, campaign_id, channel, message_type, content, sent_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (client_id, campaign_id, channel, 1, message_content, datetime.now(), "sent")
        )
    
    conn.commit()
    conn.close()

def send_email(to_email, subject, body):
    """Send email via Resend"""
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": f"Abhishek <{SENDER_EMAIL}>",
                "to": to_email,
                "subject": subject,
                "text": body
            }
        )
        return response.status_code == 200
    except:
        return False

def send_sms(phone, message):
    """Send SMS via Twilio"""
    try:
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_PHONE,
            to=phone if phone.startswith("+") else f"+91{phone}"
        )
        return True
    except:
        return False

def send_whatsapp(phone, message):
    """Send WhatsApp via Twilio"""
    try:
        twilio_client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_PHONE}",
            to=f"whatsapp:{phone if phone.startswith('+') else f'+91{phone}'}"
        )
        return True
    except:
        return False

@app.route("/campaigns/<int:campaign_id>/leads", methods=["GET"])
def get_leads(campaign_id):
    """Get all leads for a campaign"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, name, email, phone, location, status, engagement_score FROM clients WHERE campaign_id = ?",
        (campaign_id,)
    )
    
    leads = cursor.fetchall()
    conn.close()
    
    return jsonify({
        "campaign_id": campaign_id,
        "total_leads": len(leads),
        "leads": [
            {
                "id": lead[0],
                "name": lead[1],
                "email": lead[2],
                "phone": lead[3],
                "location": lead[4],
                "status": lead[5],
                "engagement_score": lead[6]
            } for lead in leads
        ]
    }), 200

@app.route("/leads/<int:lead_id>", methods=["PUT"])
def update_lead(lead_id):
    """Update lead status"""
    data = request.get_json()
    status = data.get("status", "pending")
    
    score_map = {"interested": 75, "demo_booked": 100, "not_interested": 0}
    
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE clients SET status = ?, engagement_score = ? WHERE id = ?",
        (status, score_map.get(status, 0), lead_id)
    )
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "lead_id": lead_id, "new_status": status}), 200

@app.route("/campaigns/<int:campaign_id>/analytics", methods=["GET"])
def get_analytics(campaign_id):
    """Get campaign analytics"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE campaign_id = ?", (campaign_id,))
    total = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT COUNT(*) FROM clients WHERE campaign_id = ? AND status IN ('interested', 'demo_booked')",
        (campaign_id,)
    )
    interested = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "total_leads": total,
        "interested_leads": interested,
        "conversion_rate": (interested / total * 100) if total > 0 else 0,
        "status": "active"
    }), 200

# Auto-send follow-ups every 30 mins
def schedule_followups():
    while True:
        time.sleep(1800)  # 30 minutes
        # Follow-up logic here
        pass

if __name__ == "__main__":
    # Start background thread
    threading.Thread(target=schedule_followups, daemon=True).start()
    
    # Run Flask app
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False
