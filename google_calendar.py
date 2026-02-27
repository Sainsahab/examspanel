
import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials   
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    creds = None

    if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json'
            , SCOPES)

    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json()
                        )
 
    service = build('calendar', 'v3', credentials=creds)
    return service

def add_event_to_calendar(title, description, start_date, end_date=None):
    """Add an event to Google Calendar"""
    service = get_calendar_service()
    if not end_date:
        

        end_date = start_date + datetime.timedelta(hours=1)

    event = {
        'summary': title,
        'description': description,
        'start': {
            'dateTime': start_date.isoformat(),
            'timeZone': 'America/New_York',  
        },
        'end': {
            'dateTime': end_date.isoformat(),
            'timeZone': 'America/New_York',
        },
    }

    event = service.events().insert(calendarId='primary', body=event).execute()
    print('Event created: %s' % event.get('htmlLink'))
    return event.get('htmlLink')



