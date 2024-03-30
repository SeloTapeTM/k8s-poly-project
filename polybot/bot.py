import json
import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from img import img_proc


# Static Helper Methods
def upload_file(file_name, bucket, object_name=None):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = os.path.basename(file_name)

    # Upload the file
    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
    except ClientError as e:
        logging.error(e)
        return False
    return True


class Bot:

    def __init__(self, token, telegram_chat_url):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)

        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)

        # set the webhook URL
        self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60)

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads the photos that sent to the Bot to `photos` directory (should be existed)
        :return:
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class ObjectDetectionBot(Bot):
    def __init__(self, token, telegram_chat_url):
        super().__init__(token, telegram_chat_url)
        self.processing_completed = True
        self.s3_client = boto3.client('s3')

    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')
        if "photo" in msg:
            # If the message contains a photo, check if it also has a caption
            if "caption" in msg:
                caption = msg["caption"]
                if "blur" in caption.lower() or "טשטוש" in caption.lower():
                    logger.info("Received photo with blur caption.")
                    self.process_image_blur(msg)
                elif "contour" in caption.lower() or "קווי מתאר" in caption.lower():
                    logger.info("Received photo with contour caption.")
                    self.process_image_contur(msg)
                elif ("salt n pepper" in caption.lower() or "salt and pepper" in caption.lower()
                      or "מלח פלפל" in caption.lower()):
                    logger.info("Received photo with salt n pepper caption.")
                    self.process_image_salt_n_pepper(msg)
                elif "segment" in caption.lower() or "חלוקה" in caption.lower():
                    logger.info("Received photo with segment caption.")
                    self.process_image_segment(msg)
                elif "detect" in caption.lower() or "זיהוי" in caption.lower():
                    logger.info("Received photo with detect caption.")
                    self.detect_objects_in_img(msg)
                else:
                    logger.info("Received photo with wrong caption.")
                    response = (f'Oh no!\nThe filter that you\'ve specified does not exist yet.\n Please send it again '
                                f'with the fiter you want to apply in the \"caption\" of the picture from the list of f'
                                f'ilters.\n\nFor the list of available filters you can type \"/actions\"')
                    self.send_text(msg['chat']['id'], response)

            else:
                logger.info("Received photo without a caption.")
                response = (f'Oh no!\nThe photo that you\'ve sent does not contain any filters in the caption.\n Please'
                            f' send it again with the fiter you want to apply in the \"caption\" of the picture.\n\nFor'
                            f' the list of available filters you can type \"/actions\"')
                self.send_text(msg['chat']['id'], response)
        elif "text" in msg:
            message = msg['text'].lower()
            if '/start' in message:
                logger.info("Received text with command /start.")
                response = (f'Oh, Hi there!\nWelcome to Omer\'s Image Processing Bot!\n\nFor information on how to use '
                            f'the bot type \"/help\".\nFor the list of actions type \"/actions\".')
                self.send_text(msg['chat']['id'], response)
            elif '/help' in message:
                logger.info("Received text with command /help.")
                response = (f'In order to use the bot properly you should send any photo, and in the \"caption'
                            f'\" type in the name of the action you want to apply.\n\nFor the list of actions available'
                            f' right now you can type \"/actions\".')
                self.send_text(msg['chat']['id'], response)
            elif '/actions' in message:
                logger.info("Received text with command /actions.")
                response = (f'The list of actions\\filters is:\n\nBlur - Blurs the image.\nContour - Shows only outline'
                            f's.\nSalt n Pepper - Randomly place white and black pixels over the picture.\nSegment -'
                            f' Makes all the bright parts white and all the dark parts black.\n\nNEW!!!\nDetect - detec'
                            f'ts objects in the given photo and prints what\'s detected. \n\nFor information on how'
                            f' to use the actions you can type \"/help\".')
                self.send_text(msg['chat']['id'], response)
            elif 'i hate you' in message:
                logger.info("Received text that says \"i hate you\".")
                response = f'You\'ve insulted me! And that is not nice at all.. You should be ashamed of yourself.'
                self.send_text(msg['chat']['id'], response)
            elif 'i love you' in message:
                logger.info("Received text that says \"i love you\".")
                response = f'Awwww, I love you too! <3 XOXO'
                self.send_text(msg['chat']['id'], response)
            elif 'supercalifragilisticexpialidocious' in message:
                logger.info("Received easteregg.")
                response = f'https://boulderbugle.com/super-secret-easter-egg-39tz7pni'
                self.send_text(msg['chat']['id'], response)
            elif 'supercalifragilisticexpialodocious' in message:
                logger.info("Received easteregg.")
                response = f'https://boulderbugle.com/super-secret-easter-egg-39tz7pni'
                self.send_text(msg['chat']['id'], response)
            else:
                response = (f'What you\'ve typed (\"{msg["text"]}\") is not a recognisable command.\n\nTry typing '
                            f'\"/help\"')
                self.send_text(msg['chat']['id'], response)

    def detect_objects_in_img(self, msg):
        photo_path = self.download_user_photo(msg)
        photo_name = '.'.join(photo_path.split('.')[:-1]).split('/')[1]
        bucket = 'omers3bucketpublic'
        img_name = f'{photo_name}-{datetime.now().strftime("%f")}.jpeg'
        # upload the photo to S3
        upload_response = upload_file(photo_path, bucket, img_name)
        if not upload_response:
            raise ClientError
        else:
            logger.info(f'Successfully uploaded {photo_path} to {bucket}/{img_name}')
        # send a job to the SQS queue
        time.sleep(3)

        # Create an SQS client
        sqs = boto3.client('sqs', region_name='eu-central-1')
        # Your SQS queue URL (replace with your actual SQS queue URL)
        queue_url = 'https://sqs.eu-central-1.amazonaws.com/352708296901/omerd-aws'

        # Create a message with a custom message ID
        chat_id = str(msg["chat"]["id"])
        # message_id = img_name
        msg_dict = {"chat_id": chat_id, "img_name": img_name}
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(msg_dict)
        )
        # Check for a successful response (optional)
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            print(f"Message with img name {img_name} and chat ID {chat_id} sent successfully.")
            logger.info(f"Message with img name {img_name} and chat ID {chat_id} sent successfully.")
        # send message to the Telegram end-user (e.g. Your image is being processed. Please wait...)
        self.send_text(msg['chat']['id'], 'Your image is now being processed. Please wait...')

    def process_image_segment(self, msg):
        self.processing_completed = False
        self.send_text(msg['chat']['id'], text=f'Processing...')

        # Download the two photos sent by the user
        image_path = self.download_user_photo(msg)

        # Create two different Img objects from the downloaded images
        image = img_proc.Img(image_path)

        # Process the image using your custom methods (e.g., apply filter)
        image.segment()  # rotate the image

        # Save the processed image to the specified folder
        processed_image_path = image.save_img()

        if processed_image_path is not None:
            # Send the processed image back to the user
            self.send_text(msg['chat']['id'], text=f'Completed!\nHere\'s the result:')
            self.send_photo(msg['chat']['id'], processed_image_path)

        self.processing_completed = True

    def process_image_blur(self, msg):
        self.processing_completed = False
        self.send_text(msg['chat']['id'], text=f'Processing...')

        # Download the two photos sent by the user
        image_path = self.download_user_photo(msg)

        # Create two different Img objects from the downloaded images
        image = img_proc.Img(image_path)

        # Process the image using your custom methods (e.g., apply filter)
        image.blur()  # Blurs the image

        # Save the processed image to the specified folder
        processed_image_path = image.save_img()

        if processed_image_path is not None:
            # Send the processed image back to the user
            self.send_text(msg['chat']['id'], text=f'Completed!\nHere\'s the result:')
            self.send_photo(msg['chat']['id'], processed_image_path)

        self.processing_completed = True

    def process_image_contur(self, msg):
        self.processing_completed = False
        self.send_text(msg['chat']['id'], text=f'Processing...')

        # Download the two photos sent by the user
        image_path = self.download_user_photo(msg)

        # Create two different Img objects from the downloaded images
        image = img_proc.Img(image_path)

        # Process the image using your custom methods (e.g., apply filter)
        image.contour()  # contur the image

        # Save the processed image to the specified folder
        processed_image_path = image.save_img()

        if processed_image_path is not None:
            # Send the processed image back to the user
            self.send_text(msg['chat']['id'], text=f'Completed!\nHere\'s the result:')
            self.send_photo(msg['chat']['id'], processed_image_path)

        self.processing_completed = True

    def process_image_salt_n_pepper(self, msg):
        self.processing_completed = False
        self.send_text(msg['chat']['id'], text=f'Processing...')

        # Download the two photos sent by the user
        image_path = self.download_user_photo(msg)

        # Create two different Img objects from the downloaded images
        image = img_proc.Img(image_path)

        # Process the image using your custom methods (e.g., apply filter)
        image.salt_n_pepper()  # rotate the image

        # Save the processed image to the specified folder
        processed_image_path = image.save_img()

        if processed_image_path is not None:
            # Send the processed image back to the user
            self.send_text(msg['chat']['id'], text=f'Completed!\nHere\'s the result:')
            self.send_photo(msg['chat']['id'], processed_image_path)

        self.processing_completed = True
