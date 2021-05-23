import base64
import json
import requests
import re
import os
from typing import Dict
from data import Event, Data, JobState, JsonPayload
from _logging import get_logger
from googleapiclient.discovery import build

ml = build('ml', 'v1')
GCP_PROJECT = os.environ.get('GCP_PROJECT')


def check_job_state(data):
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
    details = message.get('job_error_message', '')
    if details:
        details = f'\n> `{details}`\n'
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
    job = check_job_state(data)
    email = extract_email_from_job(job)
    message = {'email': email, 'job_id': job['jobId'], 'job_error_message': job.get('errorMessage'), 'job_state': job['state']}
    send_message(message)
