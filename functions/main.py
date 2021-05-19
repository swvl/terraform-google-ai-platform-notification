import base64
import json
import requests
import os
from typing import Dict, Optional
from data import Event, Data, JobState, JsonPayload
from _logging import get_logger


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

def get_slack_user_name(email: str) -> str:
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    response = requests.get(f'https://slack.com/api/users.lookupByEmail?email={email}', headers= {'Authorization': f'Bearer {bot_token}'})
    slack_user_name = response['user']['name']

    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )
    return slack_user_name

def send_message(message: Dict) -> None:
    # Set the webhook_url to the one provided by Slack when you create the webhook at https://my.slack.com/services/new/incoming-webhook/
    webhook_url = os.environ.get('SLACK_WEBHOOK_URI')
    channel_name = os.environ.get('SLACK_CHANNEL_NAME')
    slack_message_template = "@{slack_user_name} => JOB *{job_id}* state is: `{job_state}`"
    email = 'ahmed.abdelwahab@swvl.com'
    slack_user_name = get_slack_user_name(email)
    response = requests.post(
        webhook_url, data=json.dumps({
            'parse': 'full',
            'link_names': 1,
            'channel': channel_name,
            'text': slack_message_template.format(slack_user_name=slack_user_name, job_id=message['job_id'], job_state=message['job_state'])     
        }),
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code != 200:
        raise ValueError(
            'Request to slack returned an error %s, the response is:\n%s'
            % (response.status_code, response.text)
        )

def maybe_publish_message(message: Dict) -> None:

    logger = get_logger()

    send_message(message)
    logger.info("Message was published.")


def main(event_dict: Dict, context) -> Dict:

    logger = get_logger()

    logger.info(f"Event: {json.dumps(event_dict, indent=2)}")
    logger.info(f"Context: {context}")

    # Cast event from dict to Event instance.
    event = Event(**event_dict)

    # Extract Base64 data from event.
    data_str = base64.b64decode(event.data).decode("utf-8").strip()
    data_dict = json.loads(data_str)

    logger.info(f"Data: {json.dumps(data_dict, indent=2)}")

    # Cast data from dict to Data instance.
    data = Data(**data_dict)

    job_state = check_job_state(data)

    if job_state is None:
        logger.info(f"Message was not published because job state is {job_state}")
        return {}

    output_message = {
        "job_id": data.resource.labels.job_id,
        "project_id": data.resource.labels.project_id,
        "timestamp": data.timestamp,
        "job_state": job_state.value,
    }

    logger.info(f"Output message: {json.dumps(output_message, indent=2)}")

    # Publish message to Pub/Sub topic for notification.
    maybe_publish_message(output_message)

    return {}
