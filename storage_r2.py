# =============================================================================
# RNMS — storage_r2.py
# Cloudflare R2 (S3-compatible) से फ़ाइल अपलोड/डाउनलोड/डिलीट करने के लिए helper।
# इस पूरी फ़ाइल को अपने repo के मुख्य फ़ोल्डर में (app.py के बराबर वाली जगह)
# "storage_r2.py" नाम से रख दें।
#
# यह चार Environment Variables पढ़ता है (जो आपने Render में पहले ही डाल दिए हैं):
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
#
# requirements.txt में एक नई लाइन जोड़नी होगी: boto3
# =============================================================================

import os
import uuid
import boto3
from botocore.client import Config

BUCKET = os.environ.get("R2_BUCKET_NAME", "rnms-documents")

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def _get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_file(file_storage, related_type, related_id, doc_category):
    """
    file_storage: request.files["file"] से मिला Werkzeug FileStorage object
    return: object_key (बाद में download/delete के लिए ज़रूरी, documents तालिका में सेव होगा)
    """
    ext = os.path.splitext(file_storage.filename)[1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    object_key = f"{related_type.lower()}/{related_id}/{doc_category.lower()}/{unique_name}"

    client = _get_r2_client()
    client.upload_fileobj(
        file_storage,
        BUCKET,
        object_key,
        ExtraArgs={"ContentType": file_storage.content_type or "application/octet-stream"},
    )
    return object_key


def get_download_url(object_key, expires_in=300):
    """एक अस्थायी (5 मिनट में expire होने वाला) निजी लिंक बनाता है — bucket Private है, इसलिए सीधा public URL काम नहीं करेगा।"""
    client = _get_r2_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": object_key},
        ExpiresIn=expires_in,
    )


def delete_file(object_key):
    client = _get_r2_client()
    client.delete_object(Bucket=BUCKET, Key=object_key)
