import base64
import json
import os

from PIL import Image, ImageDraw, ImageFont
from cloudevents.http import CloudEvent
import functions_framework

from google.cloud import pubsub_v1
from google.cloud import storage
from google.cloud import translate_v2 as translate
from google.cloud import vision


vision_client = vision.ImageAnnotatorClient()
translate_client = translate.Client()
publisher = pubsub_v1.PublisherClient()
storage_client = storage.Client()

project_id = os.environ.get("GCP_PROJECT")

def add_caption_to_image(image_path, text, output_path):
    """Adds a caption to the image."""
    image = Image.open(image_path)
    draw = ImageDraw.Draw(image)
    
    # Load a font
    font = ImageFont.load_default()  # You can also load a custom TTF font
    
    # Calculate text size and position
    text_width, text_height = draw.textsize(text, font=font)
    width, height = image.size
    position = (width // 2 - text_width // 2, height - text_height - 10)
    
    # Draw text on image
    draw.text(position, text, (255, 255, 255), font=font)
    
    # Save the modified image
    image.save(output_path)

@functions_framework.cloud_event
def save_result(cloud_event: CloudEvent) -> None:
    """Cloud Function triggered by PubSub when a message is received from
    a subscription.

    Saves translated text as a caption on the original image and uploads the modified image.
    """
    expected_type = "google.cloud.pubsub.topic.v1.messagePublished"
    received_type = cloud_event["type"]
    if received_type != expected_type:
        raise ValueError(f"Expected {expected_type} but received {received_type}")

    data = cloud_event.data["message"]["data"]
    try:
        message_data = base64.b64decode(data)
        message = json.loads(message_data)

        text = message["text"]
        filename = message["filename"]
        lang = message["lang"]
    except Exception as e:
        raise ValueError(f"Missing or malformed PubSub message {data}: {e}.")

    print(f"Received request to process file {filename}.")

    # Download the original image from Cloud Storage
    bucket_name = os.environ["RESULT_BUCKET"]
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(filename)
    downloaded_image_path = f"/tmp/{filename}"
    blob.download_to_filename(downloaded_image_path)

    # Modify the image to include the translated text as a caption
    result_filename = f"{filename}_{lang}.jpg"
    output_image_path = f"/tmp/{result_filename}"
    add_caption_to_image(downloaded_image_path, text, output_image_path)

    # Upload the modified image back to Cloud Storage
    result_blob = bucket.blob(result_filename)
    result_blob.upload_from_filename(output_image_path)

    print(f"File saved with translated text: {result_filename}")

