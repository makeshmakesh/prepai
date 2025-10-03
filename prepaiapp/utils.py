# pylint:disable=all
import os
import boto3
from django.conf import settings
from botocore.exceptions import ClientError, NoCredentialsError
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def upload_to_s3(file, folder="bot-avatars"):
    """
    Upload file to S3 and return the public URL.
    Assumes bucket is already configured for public access.
    """
    if not file:
        return None

    try:
        # Generate unique filename
        file_extension = Path(file.name).suffix.lower()
        unique_filename = f"{folder}/{uuid.uuid4()}{file_extension}"

        # Initialize S3 client
        # Try to use IAM role first (for EC2), fallback to env variables
        try:
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=settings.AWS_S3_REGION_NAME,
            )

        except NoCredentialsError:
            return None

        # Determine content type
        content_type = file.content_type or "application/octet-stream"

        # Upload file
        s3_client.upload_fileobj(
            file,
            settings.AWS_STORAGE_BUCKET_NAME,
            unique_filename,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "max-age=31536000",  # Cache for 1 year
            },
        )

        # Generate public URL
        # Use custom domain if set, otherwise use standard S3 URL
        if hasattr(settings, "AWS_S3_CUSTOM_DOMAIN") and settings.AWS_S3_CUSTOM_DOMAIN:
            file_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{unique_filename}"
        else:
            file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{unique_filename}"

        logger.info(f"Successfully uploaded file to S3: {unique_filename}")
        return file_url

    except NoCredentialsError:
        logger.error(
            "No AWS credentials found. Check IAM role or environment variables."
        )
        return None
    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error uploading to S3: {e}")
        return None