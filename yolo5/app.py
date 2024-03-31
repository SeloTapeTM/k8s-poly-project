import json
import time
from pathlib import Path
import requests
from detect import run
import yaml
from loguru import logger
import boto3
from decimal import Decimal


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

TELEGRAM_APP_URL = secrets["TELEGRAM_APP_URL_K8S"]  # os.environ['TELEGRAM_APP_URL']

images_bucket = 'omers3bucketpublic'
queue_name = 'omerd-aws'

sqs_client = boto3.client('sqs', region_name='eu-central-1')

with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']


def consume():
    while True:
        response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)
        logger.info(f'response: {response}')

        if 'Messages' in response:
            message = response['Messages'][0]['Body'].split(' ')[0]
            receipt_handle = response['Messages'][0]['ReceiptHandle']

            # get dict
            msg_body = json.loads(response['Messages'][0]['Body'])

            # Use the ReceiptHandle as a prediction UUID
            prediction_id = response['Messages'][0]['MessageId']
            logger.info(f'message: {message}')
            logger.info(f'prediction: {prediction_id}. start processing')

            # Receives a URL parameter representing the image to download from S3
            img_name = msg_body["img_name"]
            chat_id = msg_body["chat_id"]
            logger.info(f'chat_id {chat_id}')
            original_img_path = img_name.split("/")[-1]
            s3_client = boto3.client('s3')
            logger.info(f'images_bucket {images_bucket} , img_name {img_name} ,'
                        f' original_img_path {original_img_path}')
            s3_client.download_file(images_bucket, img_name, original_img_path)
            logger.info(f'prediction: {prediction_id}/{original_img_path}. Download img completed')

            # Predicts the objects in the image
            run(
                weights='yolov5s.pt',
                data='data/coco128.yaml',
                source=original_img_path,
                project='static/data',
                name=prediction_id,
                save_txt=True
            )

            logger.info(f'prediction: {prediction_id}/{original_img_path}. done')

            # This is the path for the predicted image with labels The predicted image typically includes bounding
            # boxes drawn around the detected objects, along with class labels and possibly confidence scores.
            predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')
            predicted_img_name = f'predicted_{original_img_path}'
            logger.info(f'before upload, gonna upload {predicted_img_path} with filename {predicted_img_name}')
            s3_client.upload_file(predicted_img_path, images_bucket, predicted_img_name)
            logger.info(f'Upload successful')
            # Uploads the predicted image (predicted_img_path) to S3 (be careful not to override the original
            #  image).

            # Parse prediction labels and create a summary
            pred_summary_path = Path(f'static/data/{prediction_id}/labels/{original_img_path.split(".")[0]}.txt')
            if pred_summary_path.exists():
                with open(pred_summary_path) as f:
                    labels = f.read().splitlines()
                    labels = [line.split(' ') for line in labels]
                    labels = [{
                        'class': names[int(l[0])],
                        'cx': float(l[1]),
                        'cy': float(l[2]),
                        'width': float(l[3]),
                        'height': float(l[4]),
                    } for l in labels]

                labels_dic = {}
                for label in labels:
                    try:
                        labels_dic[label['class']] += 1
                    except KeyError:
                        labels_dic.update({label['class']: 1})

                summary_label = ''
                for key in labels_dic.keys():
                    summary_label = summary_label + key + ": " + labels_dic[key].__str__() + "\n"

                logger.info(f'prediction: {prediction_id}/{original_img_path}. prediction summary:\n\n{labels}')
                db_labels = json.loads(json.dumps(labels), parse_float=Decimal)
                logger.info(f'db_labels', db_labels)
                logger.info(f'db_labels', json.dumps(labels))
                prediction_summary = {
                    'prediction_id': prediction_id,
                    'original_img_path': original_img_path,
                    'predicted_img_path': predicted_img_name,
                    'labels': db_labels,
                    'time': Decimal(time.time()),
                    'detected_objects': summary_label,
                    'chat_id': chat_id
                }
                logger.info(f'prediction summery:\n\n {prediction_summary}')
                # store the prediction_summary in a DynamoDB table
                dynamodb = boto3.resource('dynamodb', region_name='eu-central-1')
                table_name = 'omerd-aws'
                table = dynamodb.Table(table_name)
                table.put_item(Item=prediction_summary)

                # perform a GET request to Polybot to `/results` endpoint
                # requests.get(f'http://{TELEGRAM_APP_URL}/results?predictionId={prediction_id}&chatId={chat_id}')
                logger.info(f'before post')
                time.sleep(2)
                requests.get(f'http://polybot-svc:8443/results/?predictionId={prediction_id}&chatId={chat_id}')
                logger.info(f'after post')

            # Delete the message from the queue as the job is considered as DONE
            sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)

        time.sleep(5)


if __name__ == "__main__":
    consume()
