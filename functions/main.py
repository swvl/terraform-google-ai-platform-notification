import base64
import json
import requests
import re
import os
from typing import Dict, Optional
from .data import Event, Data, JobState, JsonPayload
from ._logging import get_logger
from googleapiclient.discovery import build

ml = build('ml', 'v1')
GCP_PROJECT = os.environ.get('GCP_PROJECT')




def check_job_state(data: Data) -> Optional[JobState]:

    if isinstance(data.textPayload, str):
        if "completed successfully" in data.textPayload:
            return JobState.SUCCEEDED
        elif "failed" in data.textPayload:
            return JobState.FAILED
        elif "cancelled" in data.textPayload:
            return JobState.CANCELLED

    elif isinstance(data.jsonPayload, JsonPayload):
        if "queued" in data.jsonPayload.message:
            return JobState.QUEUED

    else:
        return None


def get_job_json(data):
    logger = get_logger()
    projectName = data.resource.labels.project_id
    projectId = 'projects/{}'.format(projectName)
    jobName = data.resource.labels.job_id
    jobId = '{}/jobs/{}'.format(projectId, jobName)
    request = ml.projects().jobs().get(name=jobId)
    response = None
    try:
        response = request.execute()
    except Exception as err:
        # Something went wrong. Handle the exception in an appropriate
        #  way for your application.
        raise err
    if response is None:
        raise Exception(f'Got no response for {jobId}')
    logger.info(f'Response: {json.dumps(response)}')
    return response


def get_slack_user_name(email: str) -> str:
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    response = requests.get(f'https://slack.com/api/users.lookupByEmail?email={email}', headers= {'Authorization': f'Bearer {bot_token}'})
    
    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )
    print(f'getting slack name {response.json()}')
    slack_user_name = response.json()['user']['name']
    return slack_user_name

def get_message(message: Dict) -> str:
    global GCP_PROJECT
    slack_message_template = "{slack_user_name} => JOB *{job_id}* state is: `{job_state}`{details}\n{job_link} "
    email = message.get('email')
    slack_user_name = ''
    if email:
        slack_user_name = f'@{get_slack_user_name(email)}' 
    details = message.get('job_error_message')
    if details:
        details = f'\n> `{details}`\n'
    else:
        details = ''
    job_link = f'https://console.cloud.google.com/ai-platform/jobs/{message["job_id"]}/charts/cpu?project={GCP_PROJECT}'
    return slack_message_template.format(slack_user_name=slack_user_name, job_id=message['job_id'], job_state=message['job_state'], details=details, job_link=job_link) 

def send_message(message: Dict) -> None:
    # Set the webhook_url to the one provided by Slack when you create the webhook at https://my.slack.com/services/new/incoming-webhook/
    webhook_url = os.environ.get('SLACK_WEBHOOK_URI')
    channel_name = os.environ.get('SLACK_CHANNEL_NAME')
    response = requests.post(
        webhook_url, data=json.dumps({
            'parse': 'full',
            'link_names': 1,
            'channel': channel_name,
            'text': get_message(message)     
        }),
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )

def extract_email_from_job(job):
    args = job['trainingInput']['args']
    for arg in args:
        result = re.search('--email(?:=| )(.+)', arg)
        if result:
            return result.group(1)
    return None

def main(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    logger = get_logger()
    pubsub_message = base64.b64decode(event['data']).decode('utf-8')
    logger.info(f'Event: {json.dumps(event)}')
    event_data = json.loads(pubsub_message)
    data = Data(**event_data)
    logger.info(f'data: {json.dumps(event_data)}')
    job = get_job_json(data)
    job_state = check_job_state(data)
    if not job_state:
        logger.info('Job state is none, not sending a message')
        return
    email = extract_email_from_job(job)
    message = {'email': email, 'job_id': job['jobId'], 'job_error_message': job.get('errorMessage'), 'job_state': job_state}
    send_message(message)

main({"@type": "type.googleapis.com/google.pubsub.v1.PubsubMessage", "attributes": {"logging.googleapis.com/timestamp": "2021-05-23T23:57:10.343201317Z"}, "data": "eyJpbnNlcnRJZCI6IjEweDJhcmtjdGM1IiwibGFiZWxzIjp7Im1sLmdvb2dsZWFwaXMuY29tL2VuZHBvaW50IjoiIn0sImxvZ05hbWUiOiJwcm9qZWN0cy9zd3ZsLXNhbmRib3gvbG9ncy9tbC5nb29nbGVhcGlzLmNvbSUyRnRlc3RfZHVyYXRpb25zX3BhcmFsbGVsXzEiLCJyZWNlaXZlVGltZXN0YW1wIjoiMjAyMS0wNS0yM1QyMzo1NzoxMS4xMzE3OTIyMjFaIiwicmVzb3VyY2UiOnsibGFiZWxzIjp7ImpvYl9pZCI6InRlc3RfZHVyYXRpb25zX3BhcmFsbGVsXzEiLCJwcm9qZWN0X2lkIjoic3d2bC1zYW5kYm94IiwidGFza19uYW1lIjoic2VydmljZSJ9LCJ0eXBlIjoibWxfam9iIn0sInNldmVyaXR5IjoiSU5GTyIsInRleHRQYXlsb2FkIjoiV2FpdGluZyBmb3IgdHJhaW5pbmcgcHJvZ3JhbSB0byBzdGFydC4iLCJ0aW1lc3RhbXAiOiIyMDIxLTA1LTIzVDIzOjU3OjEwLjM0MzIwMTMxN1oifQ=="}, None)