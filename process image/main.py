import base64
import json
import os

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

def detect_text(bucket: str, filename: str) -> None:
    """Extract the text from an image uploaded to Cloud Storage, then
    publish messages requesting subscribing services translate the text
    to each target language and save the result.

    Args:
        bucket: name of GCS bucket in which the file is stored.
        filename: name of the file to be read.
    """

    print(f"Looking for text in image {filename}")

    # Use the Vision API to extract text from the image
    image = vision.Image(
        source=vision.ImageSource(gcs_image_uri=f"gs://{bucket}/{filename}")
    )
    text_detection_response = vision_client.text_detection(image=image)
    annotations = text_detection_response.text_annotations

    if annotations:
        text = annotations[0].description
    else:
        text = ""
    print(f"Extracted text {text} from image ({len(text)} chars).")

    detect_language_response = translate_client.detect_language(text)
    src_lang = detect_language_response["language"]
    print(f"Detected language {src_lang} for text {text}.")

    # Submit a message to the bus for each target language
    futures = []  # Asynchronous publish request statuses

    to_langs = os.environ.get("TO_LANG", "").split(",")
    for target_lang in to_langs:
        topic_name = os.environ.get("TRANSLATE_TOPIC")
        if src_lang == target_lang or src_lang == "und":
            topic_name = os.environ.get("RESULT_TOPIC")

        message = {
            "text": text,
            "filename": filename,
            "lang": target_lang,
            "src_lang": src_lang,
        }

        message_data = json.dumps(message).encode("utf-8")
        topic_path = publisher.topic_path(project_id, topic_name)
        future = publisher.publish(topic_path, data=message_data)
        futures.append(future)

    # Wait for each publish request to be completed before exiting
    for future in futures:
        future.result()

@functions_framework.cloud_event
def process_image(cloud_event: CloudEvent) -> None:
    """Cloud Function triggered by Cloud Storage when a file is changed.

    Gets the names of the newly created object and its bucket then calls
    detect_text to find text in that image.

    detect_text finishes by sending PubSub messages requesting another service
    then complete processing those texts by translating them and saving the
    translations.
    """

    # Check that the received event is of the expected type, return error if not
    expected_type = "google.cloud.storage.object.v1.finalized"
    received_type = cloud_event["type"]
    if received_type != expected_type:
        raise ValueError(f"Expected {expected_type} but received {received_type}")

    # Extract the bucket and file names of the uploaded image for processing
    data = cloud_event.data
    bucket = data["bucket"]
    filename = data["name"]

    # Process the information in the new image
    detect_text(bucket, filename)

    print(f"File {filename} processed.")
