# requirements: pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib beautifulsoup4
import os
import re
import csv
import base64
from datetime import datetime
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Gmail scope: readonly is sufficient for scraping
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_PATH = 'token.json'
CREDS_PATH = 'credentials.json'

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def search_messages(service, user_id='me', query=''):
    try:
        resp = service.users().messages().list(userId=user_id, q=query).execute()
        return resp.get('messages', [])
    except Exception as e:
        print(f"An error occurred during search: {e}")
        return []

def fetch_message_body(service, msg_id, user_id='me'):
    try:
        msg = service.users().messages().get(userId=user_id, id=msg_id, format='full').execute()
        parts = msg.get('payload', {}).get('parts', [])
        body_html = ''
        
        # If the message is multipart (contains text and html), find the html part
        if parts:
            for p in parts:
                if p.get('mimeType') == 'text/html' and 'data' in p.get('body', {}):
                    data = p['body']['data']
                    body_html += base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='ignore')
        # If the message is not multipart, the body might be directly in the payload
        elif 'body' in msg.get('payload', {}) and 'data' in msg['payload']['body']:
             data = msg['payload']['body']['data']
             body_html = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='ignore')
             
        return body_html
    except Exception as e:
        print(f"Error fetching message {msg_id}: {e}")
        return None

def parse_currency(value_str):
    """Cleans string '$20.00' -> float 20.0"""
    if not value_str:
        return 0.0
    # Remove $ and commas, keep negative signs
    clean = re.sub(r'[^\d.-]', '', value_str)
    try:
        return float(clean)
    except ValueError:
        return 0.0

def determine_purchase_class(amount):
    """
    Map amount to class:
    $5 -> A, $10 -> B ... $50 -> J
    Else -> raw number
    """
    # Mapping logic: (Amount / 5) - 1 = Index in alphabet
    # 5/5 - 1 = 0 (A)
    # 50/5 - 1 = 9 (J)
    
    # Check if amount is a multiple of 5 and within 5-50 range
    if amount > 0 and amount % 5 == 0 and 5 <= amount <= 50:
        index = int((amount / 5) - 1)
        # "ABCDEFGHIJ"
        classes = "ABCDEFGHIJ"
        if 0 <= index < len(classes):
            return classes[index]
    
    return str(amount)

def extract_info_from_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    info = {}

    # 1. EXTRACT ORDER ID
    # Look for span with "Order:", get the next span
    order_label = soup.find(string=re.compile("Order:"))
    if order_label:
        # Navigate up to the parent span/p and find the next sibling or span
        # Based on snippet: <p><span>Order:</span><span>894950</span></p>
        parent = order_label.find_parent()
        if parent:
            # Try to find the next span immediately after
            next_span = parent.find_next_sibling('span') 
            # Or if they are in the same P tag, just find the next span in general
            if not next_span:
                 next_span = parent.find_next('span')
            
            if next_span:
                info['order_id'] = next_span.get_text(strip=True)

    # 2. EXTRACT DATE
    # Snippet: <span>Date/Time:</span><span>November 21, 2025 at 8:24:54 PM EST</span>
    date_label = soup.find(string=re.compile("Date/Time:"))
    if date_label:
        parent = date_label.find_parent()
        date_span = parent.find_next('span') if parent else None
        if date_span:
            raw_date = date_span.get_text(strip=True)
            # Clean "at " and timezone " EST/EDT" for parsing
            # "November 21, 2025 at 8:24:54 PM EST"
            # Simplify to "November 21, 2025" for easier parsing
            try:
                # Split by ' at ' to get just the date part
                date_part = raw_date.split(' at ')[0] 
                dt_obj = datetime.strptime(date_part, '%B %d, %Y')
                info['date'] = dt_obj.strftime('%Y-%m-%d')
            except Exception:
                info['date'] = raw_date # Fallback to raw if parse fails

    # 3. EXTRACT EMAIL (Updated Logic)
    # Strategy: Find "Contact Email:", go to next ROW, grab the text directly.
    email_label = soup.find(string=re.compile("Contact Email:"))
    if email_label:
        label_row = email_label.find_parent('tr')
        if label_row:
            data_row = label_row.find_next_sibling('tr')
            if data_row:
                # FIX: Directly get text instead of looking for 'a' tag.
                # The snippet shows: <span class="dataLabel">email@domain.com</span>
                # get_text(strip=True) will pull "email@domain.com" cleanly.
                raw_email = data_row.get_text(strip=True)
                
                # Optional: Simple cleanup if there's extra noise, 
                # but get_text is usually sufficient for this structure.
                if '@' in raw_email:
                    info['email'] = raw_email

    # 4. EXTRACT SUBTOTAL (Purchase Amount)
    # Snippet: <td>Subtotal:</td> <td>$20.00</td>
    # Note: Using 'Subtotal:' to define purchase amount as per user request
    subtotal_label = soup.find(string=re.compile("Subtotal:"))
    purchase_amount = 0.0
    if subtotal_label:
        # Find the parent TD, then the next TD
        label_td = subtotal_label.find_parent('td')
        if label_td:
            val_td = label_td.find_next_sibling('td')
            if val_td:
                purchase_amount = parse_currency(val_td.get_text(strip=True))
    
    info['purchase_amount'] = purchase_amount

    # 5. EXTRACT PROMO DISCOUNT
    # Snippet: <td>Promo Discount:</td> <td>-$20.00</td>
    promo_label = soup.find(string=re.compile("Promo Discount:"))
    promo_amount = 0.0
    if promo_label:
        label_td = promo_label.find_parent('td')
        if label_td:
            val_td = label_td.find_next_sibling('td')
            if val_td:
                # abs() because the snippet shows "-$20.00" but we usually want the magnitude for ratios
                promo_amount = abs(parse_currency(val_td.get_text(strip=True)))
    
    # 6. CALCULATED FIELDS
    # Purchase Class
    info['purchase_class'] = determine_purchase_class(purchase_amount)

    # Aid Percent (Promo / Purchase)
    if purchase_amount > 0:
        ratio = promo_amount / purchase_amount
        info['aid_percent'] = f"{ratio:.2%}" # Formats as 25.00%
    else:
        info['aid_percent'] = "0%"

    return info

def main():
    service = get_gmail_service()
    
    # UPDATE THIS QUERY to match your specific emails
    # e.g., from:receipts@uber.com or subject:"Your Trip Receipt"
    query = 'from:commerce@brown.edu' 
    
    print("Searching for messages...")
    messages = search_messages(service, query=query)
    print(f'Found {len(messages)} messages matching query')

    out_path = 'extracted_receipts.csv'
    fieldnames = ['order_id', 'date', 'email', 'purchase_class', 'aid_percent', 'purchase_amount']
    
    with open(out_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        count = 0
        for m in messages:
            try:
                html_body = fetch_message_body(service, m['id'])
                if html_body:
                    info = extract_info_from_html(html_body)
                    
                    # Only write if we actually found an order ID (filters out empty/failed parses)
                    if info and info.get('order_id'):
                        # Write only the fields we defined in the header
                        row = {k: info.get(k, '') for k in fieldnames}
                        writer.writerow(row)
                        count += 1
                        print(f"Parsed Order: {info.get('order_id')}")
            except Exception as e:
                print(f"Skipping message {m['id']} due to error: {e}")

    print(f'Done — {count} receipts saved to {out_path}')

if __name__ == '__main__':
    main()