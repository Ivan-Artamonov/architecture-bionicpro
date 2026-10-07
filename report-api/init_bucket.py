"""Create the private reports bucket once MinIO is ready."""
import os
import time

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

s3 = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT", "http://minio:9000"),
                  aws_access_key_id=os.environ["MINIO_ROOT_USER"],
                  aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"])
for _ in range(60):
    try:
        s3.create_bucket(Bucket=os.getenv("S3_BUCKET", "reports"))
        break
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            break
        raise
    except EndpointConnectionError:
        time.sleep(2)
else:
    raise RuntimeError("MinIO did not become ready")
