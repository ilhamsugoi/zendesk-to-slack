import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_DOMAIN = os.getenv("ZENDESK_DOMAIN")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

@app.route('/zendesk-webhook', methods=['POST'])
def zendesk_webhook():
    data = request.json
    ticket = data.get("ticket", data)
    ticket_id = ticket.get("id")
    requester = ticket.get("requester", {})
    via = ticket.get("via", {})
    subject = ticket.get("subject", "-")
    status = ticket.get("status", "-")

    # Step 1: Fetch all comments
    url = f"https://{ZENDESK_DOMAIN}/api/v2/tickets/{ticket_id}/comments.json"
    auth = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)
    resp = requests.get(url, auth=auth)
    if resp.status_code != 200:
        print("Failed to get comments", resp.text)
        return "error", 500

    comments = resp.json()["comments"]

    # Step 2: Get author names (unique)
    author_ids = {c["author_id"] for c in comments}
    author_names = {}
    for author_id in author_ids:
        user_url = f"https://{ZENDESK_DOMAIN}/api/v2/users/{author_id}.json"
        user_resp = requests.get(user_url, auth=auth)
        if user_resp.status_code == 200:
            author_names[author_id] = user_resp.json()["user"]["name"]
        else:
            author_names[author_id] = f"User {author_id}"

    # Step 3: Build Slack Block Kit
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Ticket ID:* {ticket_id}\n"
                        f"*Requester:* {requester.get('name', '-')}\n"
                        f"*Channel:* {via.get('channel', '-')}\n"
                        f"*Phone Number:* {requester.get('phone', '-')}\n"
                        f"*Email:* {requester.get('email', '-')}\n"
                        f"*Subject:* {subject}\n"
                        f"*Status:* {status}\n"
                        f"*Link:* <https://{ZENDESK_DOMAIN}/agent/tickets/{ticket_id}|Lihat tiket di Zendesk>"
            }
        },
        {"type": "divider"},
        {"type": "header", "text": {"type": "plain_text", "text": "Percakapan Tiket"}}
    ]

    for c in comments:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{author_names.get(c['author_id'], 'Unknown')}* "
                        f"({c['created_at']}):\n{c.get('plain_body', '')}"
            }
        })
        # Lampirkan semua attachment pada comment ini
        for att in c.get("attachments", []):
            blocks.append({
                "type": "image",
                "image_url": att["content_url"],
                "alt_text": att["file_name"]
            })

    slack_payload = {"blocks": blocks}
    slack_resp = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
    if slack_resp.status_code >= 300:
        print("Failed to post to Slack", slack_resp.text)
        return "error", 500

    return "OK"

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
