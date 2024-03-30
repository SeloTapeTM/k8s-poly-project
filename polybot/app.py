import flask
from flask import request
import os
from bot import ObjectDetectionBot
import json
import boto3
from botocore.exceptions import ClientError
from loguru import logger

app = flask.Flask(__name__)


# Static Helper Methods
def get_secret():
    secret_name = "omerd-secret-tg"
    region_name = "eu-central-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


# load TELEGRAM_TOKEN value from Secret Manager
secrets = get_secret()
TELEGRAM_TOKEN = secrets["TELEGRAM_TOKEN"]  # os.environ['TELEGRAM_TOKEN']

TELEGRAM_APP_URL = secrets["TELEGRAM_APP_URL"]  # os.environ['TELEGRAM_APP_URL']


@app.route('/', methods=['GET'])
def index():
    return 'Ok'


@app.route(f'/{TELEGRAM_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'


@app.route(f'/results/', methods=['GET'])
def results():
    prediction_id = request.args.get('predictionId')
    logger.info(f'prediction_id: {prediction_id}')
    # use the prediction_id to retrieve results from DynamoDB and send to the end-user

    # Initialize the DynamoDB client
    dynamodb = boto3.resource('dynamodb', region_name='eu-central-1')
    table_name = 'omerd-aws'  # Replace with your table name
    table = dynamodb.Table(table_name)

    # Define your primary key
    primary_key = {
        'prediction_id': str(prediction_id)
        # Replace with the actual primary key attribute name and value
    }
    logger.info(f'primary_key: {primary_key}')
    # Use the get_item method to fetch the item
    response = table.get_item(Key=primary_key)
    logger.info(f'response: {response}')
    # Check if the item was found
    if 'Item' in response:
        item = response['Item']
        print("Item found:")
        print(item['detected_objects'])
        print(item['chat_id'])

    else:
        print("Item not found")

    chat_id = item['chat_id']
    text_results = item['detected_objects']
    text_msg = f'This is what I\'ve found in the picture that you\'ve sent me:\n\n{text_results}'

    bot.send_text(chat_id, text_msg)
    return 'Ok'


@app.route(f'/loadTest/', methods=['POST'])
def load_test():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'


if __name__ == "__main__":
    bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

    app.run(host='0.0.0.0', port=8443)
