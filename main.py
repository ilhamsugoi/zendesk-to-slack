import os
import requests
from flask import Flask, request
import pytz
from datetime import datetime

app = Flask(__name__)

ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_DOMAIN = os.getenv("ZENDESK_DOMAIN")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

def zendesk_auth():
    return (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)

def get_author_name(author_id, requester_name):
    url = f"https://{ZENDESK_DOMAIN}/api/v2/users/{author_id}.json"
    resp = requests.get(url, auth=zendesk_auth())
    if resp.status_code == 200:
        data = resp.json()["user"]
        if data.get("role") in ["admin", "agent"]:
            return data.get("name", requester_name)
        else:
            return requester_name
    else:
        print(f"Failed to get user for author_id {author_id}: {resp.text}")
        return requester_name

@app.route('/zendesk-webhook', methods=['POST'])
def zendesk_webhook():
    try:
        data = request.get_json(force=True)
        ticket = data.get("ticket", {})
        ticket_id = ticket.get("id")
        if not ticket_id:
            return "No ticket id", 400

        subject = ticket.get("subject", "-")
        status = ticket.get("status", "-")
        requester = ticket.get("requester", {})
        via = ticket.get("via", {})
        requester_name = requester.get("name", "-")
        requester_email = requester.get("email", "-")
        requester_phone = requester.get("phone", "-")
        channel = via.get("channel", "-")

        ticket_link = f"https://{ZENDESK_DOMAIN}/agent/tickets/{ticket_id}"
        ticket_id_md = f"<{ticket_link}|{ticket_id}>"

        # Fetch comments
        comments_url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/comments.json"
        resp = requests.get(comments_url, auth=zendesk_auth())
        comments = resp.json().get("comments", []) if resp.status_code == 200 else []

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Ticket ID:* {ticket_id_md}\n"
                            f"*Subject:* {subject}\n"
                            f"*Status:* {status}\n"
                            f"*Requester:* {requester_name}\n"
                            f"*Email:* {requester_email}\n"
                            f"*Phone:* {requester_phone}\n"
                            f"*Channel:* {channel}"
                }
            },
            {"type": "divider"},
            {"type": "header", "text": {"type": "plain_text", "text": "Percakapan Tiket"}}
        ]

        author_cache = {}

        for c in comments:
            author_id = c.get("author_id")
            if author_id not in author_cache:
                author_cache[author_id] = get_author_name(author_id, requester_name)
            author = author_cache[author_id]
            waktu_utc = c.get("created_at", "")
            waktu_jakarta = waktu_utc
            try:
                dt_utc = datetime.strptime(waktu_utc, "%Y-%m-%dT%H:%M:%SZ")
                dt_jkt = dt_utc.replace(tzinfo=pytz.UTC).astimezone(JAKARTA_TZ)
                waktu_jakarta = dt_jkt.strftime("%d-%m-%Y %H:%M")
            except Exception as e:
                print("Error convert waktu:", e)

            text = c.get("plain_body", "")
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{author}* ({waktu_jakarta} WIB):\n{text}"
                }
            })
            for att in c.get("attachments", []):
                blocks.append({
                    "type": "image",
                    "image_url": att["content_url"],
                    "alt_text": att["file_name"]
                })

        slack_payload = {"blocks": blocks}
        slack_resp = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
        print("RESP SLACK:", slack_resp.status_code, slack_resp.text)

        if slack_resp.status_code >= 400:
            return f"Slack error: {slack_resp.text}", 500

        return "OK", 200

    except Exception as e:
        print("ERROR PARSING:", e)
        return f"Invalid JSON: {e}", 400

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
