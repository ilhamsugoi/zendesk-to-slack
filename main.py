import os
import requests
from flask import Flask, request

app = Flask(__name__)

ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_DOMAIN = os.getenv("ZENDESK_DOMAIN")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def zendesk_auth():
    return (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)

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

        for c in comments:
            text = c.get("plain_body", "")
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
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
