import os
import requests
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import hashlib
import time

# IMOU API konfigurace
IMOU_APP_ID = os.environ.get('IMOU_APP_ID')
IMOU_APP_SECRET = os.environ.get('IMOU_APP_SECRET')
IMOU_DEVICE_ID = os.environ.get('IMOU_DEVICE_ID')
IMOU_API_URL = "https://openapi.easy4ip.com/openapi"

# Google Drive konfigurace
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')

def get_imou_access_token():
    """Získání access tokenu pro IMOU API"""
    url = f"{IMOU_API_URL}/accessToken"
    
    # Vytvoření time stamp v milisekundách
    time_ms = str(int(time.time() * 1000))
    
    # Vytvoření system parametrů
    system_params = {
        "ver": "1.0",
        "sign": "",
        "appId": IMOU_APP_ID,
        "time": time_ms
    }
    
    # Vytvoření podpisu: MD5(time + nonce + appSecret)
    # Podle IMOU dokumentace
    nonce = time_ms  # Často se používá timestamp jako nonce
    sign_string = f"{time_ms}{nonce}{IMOU_APP_SECRET}"
    signature = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
    
    system_params["sign"] = signature
    
    payload = {
        "system": system_params,
        "params": {}
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Requesting token from: {url}")
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    
    print(f"Token response: {json.dumps(data, indent=2)}")
    
    if data.get('code') == '0' or data.get('result', {}).get('code') == '0':
        # API může vracet token různými způsoby
        if 'result' in data and 'accessToken' in data['result']:
            return data['result']['accessToken']
        elif 'accessToken' in data:
            return data['accessToken']
        else:
            raise Exception(f"Token nebyl nalezen v odpovědi: {data}")
    else:
        raise Exception(f"Chyba při získávání tokenu: {data}")

def get_device_snapshot(access_token):
    """Stažení snímku z kamery"""
    url = f"{IMOU_API_URL}/device/snapshot"
    
    time_ms = str(int(time.time() * 1000))
    
    system_params = {
        "ver": "1.0",
        "appId": IMOU_APP_ID,
        "time": time_ms,
        "sign": hashlib.md5(f"{time_ms}{time_ms}{IMOU_APP_SECRET}".encode()).hexdigest()
    }
    
    payload = {
        "system": system_params,
        "params": {
            "token": access_token,
            "deviceId": IMOU_DEVICE_ID,
            "channelId": "0"
        }
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Requesting snapshot from: {url}")
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    
    print(f"Snapshot response: {json.dumps(data, indent=2)}")
    
    # Zpracování odpovědi
    if data.get('code') == '0' or (data.get('result') and data['result'].get('code') == '0'):
        # Získání URL snímku
        result = data.get('result', data)
        
        if 'url' in result:
            image_url = result['url']
        elif 'snapshots' in result and len(result['snapshots']) > 0:
            image_url = result['snapshots'][0].get('url')
        else:
            raise Exception(f"URL snímku nebyla nalezena v odpovědi: {data}")
        
        print(f"Downloading image from: {image_url}")
        
        # Stažení obrázku
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        
        return img_response.content
    else:
        raise Exception(f"Chyba při získávání snímku: {data}")

def upload_to_google_drive(image_data, filename):
    """Nahrání snímku na Google Drive pomocí Service Account"""
    
    # Parsování Service Account credentials
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    
    # Vytvoření credentials ze Service Account
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive.file']
    )
    
    service = build('drive', 'v3', credentials=credentials)
    
    # Uložení obrázku dočasně
    temp_file = f"/tmp/{filename}"
    with open(temp_file, 'wb') as f:
        f.write(image_data)
    
    print(f"Image saved temporarily to: {temp_file}")
    print(f"Image size: {len(image_data)} bytes")
    
    # Metadata souboru
    file_metadata = {
        'name': filename,
        'parents': [GOOGLE_DRIVE_FOLDER_ID]
    }
    
    media = MediaFileUpload(temp_file, mimetype='image/jpeg')
    
    print(f"Uploading to Google Drive folder: {GOOGLE_DRIVE_FOLDER_ID}")
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, name, webViewLink'
    ).execute()
    
    print(f"✓ Soubor '{filename}' nahrán s ID: {file.get('id')}")
    print(f"  Link: {file.get('webViewLink', 'N/A')}")
    
    # Smazání dočasného souboru
    os.remove(temp_file)

def main():
    """Hlavní funkce"""
    try:
        print("=" * 60)
        print("IMOU Camera Timelapse - Start")
        print("=" * 60)
        
        # Kontrola prostředí
        required_vars = ['IMOU_APP_ID', 'IMOU_APP_SECRET', 'IMOU_DEVICE_ID', 
                        'GOOGLE_DRIVE_FOLDER_ID', 'GOOGLE_CREDENTIALS_JSON']
        
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        if missing_vars:
            raise Exception(f"Chybí environment proměnné: {', '.join(missing_vars)}")
        
        print(f"App ID: {IMOU_APP_ID}")
        print(f"Device ID: {IMOU_DEVICE_ID}")
        print(f"Drive Folder ID: {GOOGLE_DRIVE_FOLDER_ID}")
        print()
        
        # 1. Získání access tokenu
        print("[1/3] Získávám IMOU access token...")
        access_token = get_imou_access_token()
        print(f"✓ Token získán: {access_token[:20]}...")
        print()
        
        # 2. Stažení snímku
        print("[2/3] Stahuji snímek z kamery...")
        image_data = get_device_snapshot(access_token)
        print(f"✓ Snímek stažen ({len(image_data)} bytes)")
        print()
        
        # 3. Vytvoření názvu souboru s časovou značkou
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"timelapse_{timestamp}.jpg"
        
        # 4. Nahrání na Google Drive
        print(f"[3/3] Nahrávám '{filename}' na Google Drive...")
        upload_to_google_drive(image_data, filename)
        print()
        
        print("=" * 60)
        print("✓ HOTOVO! Snímek byl úspěšně nahrán.")
        print("=" * 60)
        
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ CHYBA: {str(e)}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
