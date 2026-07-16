"""
QuiteCapital Outreach Platform - FastAPI Backend
Handles Email (Resend), SMS/WhatsApp (Twilio), Campaign Management, Lead Tracking
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import os
import json
from typing import List, Optional
import requests
from twilio.rest import Client as TwilioClient
import asyncio
from apscheduler.schedulers.background import BackgroundScheduler

# Environment Variables
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "re_Um464pMw_hDutC5whLpK8m6zdebvR3Er3")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "AC6017d3a5097b5ce126fc44d292a5ce82")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "TYV55GXNADK4TEEXDT5HTX18")
TWILIO_PHONE = os.getenv("TWILIO_PHONE", "+919938455252")
SENDER_EMAIL = "onboarding@quitecapital.resend.dev"
SENDER_NAME = "Abhishek"
SENDER_WHATSAPP = "+919938455252"
SENDER_EMAIL_ADDRESS = "abhishektiwari160906@gmail.com"

# Initialize FastAPI
app = FastAPI(title="QuiteCapital Outreach Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Twilio
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Database Setup
def init_db():
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY,
            campaign_id INTEGER,
            name TEXT,
            email TEXT,
            phone TEXT,
            location TEXT,
            business_type TEXT,
            message1_sent_at TIMESTAMP,
            message2_sent_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            engagement_score INTEGER DEFAULT 0,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            client_id INTEGER,
            campaign_id INTEGER,
            channel TEXT,
            message_type INTEGER,
            content TEXT,
            sent_at TIMESTAMP,
            delivered_at TIMESTAMP,
            opened_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY,
            client_id INTEGER,
            campaign_id INTEGER,
            response_text TEXT,
            received_at TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id),
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# Pydantic Models
class Client(BaseModel):
    name: str
    email: str
    phone: str
    location: str
    business_type: str = "restaurant"

class Campaign(BaseModel):
    name: str
    clients: List[Client]

class LeadUpdate(BaseModel):
    status: str  # interested, not_interested, demo_booked

# Message Templates
MESSAGE_1 = """Hi 👋 I'm Abhishek. I work with restaurants in Bhubaneswar to automate customer enquiries on WhatsApp and Instagram.

We built an AI Customer Assistant that instantly sends menus, location, offers, and collects reservations.

I thought this could be valuable for {NAME}.

Quick 10-minute demo?

📱 WhatsApp: +919938455252
📧 Email: abhishektiwari160906@gmail.com
🎬 YouTube: @quitecapital1111"""

FOLLOW_UP_TEMPLATES = {
    "uptown_vibes": "Hi Team Uptown Vibes,\n\nSince you're located on KIIT Road where customer traffic is high, many people usually message before visiting.\n\nImagine every WhatsApp or Instagram enquiry getting an instant reply—even during rush hours.\n\n✔ Digital Menu\n✔ Google Maps Location\n✔ Today's Special Combos\n✔ Automatic Table Reservations\n✔ 24×7 Customer Replies\n\nNo extra staff required.\n\nI'd love to show you how this could work specifically for Uptown Vibes. A 10-minute demo is all it takes.\n\n📱 WhatsApp: +919938455252",
    
    "lemon_grass": "Hi Team Lemon Grass,\n\nGuests staying in hotels often message before dining. A delayed response can mean losing that guest.\n\nOur AI Customer Assistant replies instantly by sending your menu, directions, today's chef specials, and collecting reservation details automatically.\n\nIt works around the clock while your staff focuses on providing a great dining experience.\n\nHappy to give you a quick 10-minute demo whenever convenient.\n\n📱 WhatsApp: +919938455252",
    
    "default": "Hi Team,\n\nJust following up on my previous message.\n\nWe help restaurants automate customer conversations on WhatsApp and Instagram.\n\nEvery enquiry gets an instant reply with your menu, Google Maps location, today's offers, and reservation booking—24 hours a day.\n\nIt's designed to help restaurants convert more enquiries into paying customers while saving staff time.\n\nIf you'd like to see it in action, I'd be happy to arrange a 10-minute demo at your convenience.\n\n📱 WhatsApp: +919938455252"
}

# API Routes
@app.get("/")
def root():
    return {"status": "QuiteCapital Outreach Platform Running"}

@app.post("/campaigns")
def create_campaign(campaign: Campaign):
    """Create new campaign and send Message 1 to all clients"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute("INSERT INTO campaigns (name, created_at, status) VALUES (?, ?, ?)", 
                      (campaign.name, datetime.now(), "active"))
        campaign_id = cursor.lastrowid
        conn.commit()
        
        # Add clients and send Message 1
        for client in campaign.clients:
            cursor.execute("""
                INSERT INTO clients (campaign_id, name, email, phone, location, business_type, message1_sent_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (campaign_id, client.name, client.email, client.phone, client.location, client.business_type, datetime.now(), "message1_sent"))
            
            client_id = cursor.lastrowid
            
            # Send Message 1 (Email + SMS + WhatsApp)
            send_message_1(client, client_id, campaign_id)
        
        conn.commit()
        conn.close()
        
        return {"status": "success", "campaign_id": campaign_id, "message": "Campaign created and Message 1 sent to all clients"}
    
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

def send_message_1(client: Client, client_id: int, campaign_id: int):
    """Send personalized Message 1 via Email, SMS, WhatsApp"""
    message_content = MESSAGE_1.replace("{NAME}", client.name)
    
    # Send Email
    send_email(client.email, "AI automation for " + client.name, message_content)
    
    # Send SMS
    send_sms(client.phone, message_content[:160])  # SMS has 160 char limit
    
    # Send WhatsApp
    send_whatsapp(client.phone, message_content)
    
    # Log messages
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    for channel in ["email", "sms", "whatsapp"]:
        cursor.execute("""
            INSERT INTO messages (client_id, campaign_id, channel, message_type, content, sent_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (client_id, campaign_id, channel, 1, message_content, datetime.now(), "sent"))
    
    conn.commit()
    conn.close()

def send_email(to_email: str, subject: str, body: str):
    """Send email via Resend"""
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
                "to": to_email,
                "subject": subject,
                "text": body
            }
        )
        return response.status_code == 200
    except:
        return False

def send_sms(phone: str, message: str):
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

def send_whatsapp(phone: str, message: str):
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

@app.get("/campaigns/{campaign_id}/leads")
def get_leads(campaign_id: int):
    """Get all leads for a campaign with engagement data"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, email, phone, location, status, engagement_score, message1_sent_at, message2_sent_at
        FROM clients WHERE campaign_id = ?
    """, (campaign_id,))
    
    leads = cursor.fetchall()
    conn.close()
    
    return {
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
                "engagement_score": lead[6],
                "message1_sent": lead[7],
                "message2_sent": lead[8]
            } for lead in leads
        ]
    }

@app.put("/leads/{lead_id}")
def update_lead(lead_id: int, update: LeadUpdate):
    """Update lead status and engagement"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    score_map = {"interested": 75, "demo_booked": 100, "not_interested": 0}
    
    cursor.execute("""
        UPDATE clients SET status = ?, engagement_score = ?
        WHERE id = ?
    """, (update.status, score_map.get(update.status, 0), lead_id))
    
    conn.commit()
    conn.close()
    
    return {"status": "success", "lead_id": lead_id, "new_status": update.status}

@app.get("/campaigns/{campaign_id}/analytics")
def get_analytics(campaign_id: int):
    """Get campaign analytics"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE campaign_id = ?", (campaign_id,))
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM clients WHERE campaign_id = ? AND status IN ('interested', 'demo_booked')", (campaign_id,))
    interested = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM messages WHERE campaign_id = ? AND channel = 'email' AND status = 'sent'", (campaign_id,))
    emails_sent = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total_leads": total,
        "interested_leads": interested,
        "emails_sent": emails_sent,
        "conversion_rate": (interested / total * 100) if total > 0 else 0,
        "status": "active"
    }

# Background scheduler for 24-hour follow-ups
scheduler = BackgroundScheduler()

def schedule_followups():
    """Schedule follow-up messages for clients 24 hours after message 1"""
    conn = sqlite3.connect("quitecapital.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, email, phone, location FROM clients
        WHERE message1_sent_at IS NOT NULL 
        AND message2_sent_at IS NULL
        AND datetime(message1_sent_at) <= datetime('now', '-24 hours')
    """)
    
    clients_to_followup = cursor.fetchall()
    
    for client in clients_to_followup:
        client_id, name, email, phone, location = client
        
        # Get campaign_id
        cursor.execute("SELECT campaign_id FROM clients WHERE id = ?", (client_id,))
        campaign_id = cursor.fetchone()[0]
        
        # Send personalized follow-up
        followup_msg = get_followup_message(name.lower())
        
        send_email(email, "Quick demo: AI automation for " + name, followup_msg)
        send_whatsapp(phone, followup_msg)
        
        # Update sent time
        cursor.execute("""
            UPDATE clients SET message2_sent_at = ? 
            WHERE id = ?
        """, (datetime.now(), client_id))
        
        # Log message
        cursor.execute("""
            INSERT INTO messages (client_id, campaign_id, channel, message_type, content, sent_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (client_id, campaign_id, "email", 2, followup_msg, datetime.now(), "sent"))
    
    conn.commit()
    conn.close()

def get_followup_message(restaurant_name: str):
    """Get personalized follow-up message"""
    for key in FOLLOW_UP_TEMPLATES.keys():
        if key != "default" and key in restaurant_name:
            return FOLLOW_UP_TEMPLATES[key]
    return FOLLOW_UP_TEMPLATES["default"]

scheduler.add_job(schedule_followups, 'interval', minutes=30)
scheduler.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
