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

@functions_framework.cloud_event
def translate_text(cloud_event: CloudEvent) -> None:
    """Cloud Function triggered by PubSub when a message is received from
    a subscription.

    Translates the text in the message from the specified source language
    to the requested target language, then sends a message requesting another
    service save the result.
    """

    # Check that the received event is of the expected type, return error if not
    expected_type = "google.cloud.pubsub.topic.v1.messagePublished"
    received_type = cloud_event["type"]
    if received_type != expected_type:
        raise ValueError(f"Expected {expected_type} but received {received_type}")

    # Extract the message body, expected to be a JSON representation of a
    # dictionary, and extract the fields from that dictionary.
    data = cloud_event.data["message"]["data"]
    try:
        message_data = base64.b64decode(data)
        message = json.loads(message_data)

        text = message["text"]
        filename = message["filename"]
        target_lang = message["lang"]
        src_lang = message["src_lang"]
    except Exception as e:
        raise ValueError(f"Missing or malformed PubSub message {data}: {e}.")

    # Translate the text and publish a message with the translation
    print(f"Translating text into {target_lang}.")

    translated_text = translate_client.translate(
        text, target_language=target_lang, source_language=src_lang
    )

    topic_name = os.environ["RESULT_TOPIC"]
    message = {
        "text": translated_text["translatedText"],
        "filename": filename,
        "lang": target_lang,
    }
    message_data = json.dumps(message).encode("utf-8")
    topic_path = publisher.topic_path(project_id, topic_name)
    future = publisher.publish(topic_path, data=message_data)
    future.result()  # Wait for operation to complete
