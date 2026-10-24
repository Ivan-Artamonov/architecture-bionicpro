import hashlib
import json
import os
import re
import time
from threading import Lock
from urllib.parse import parse_qs, urlsplit

import boto3
import jwt
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.encoders import jsonable_encoder


class SnapshotChanged(Exception):
    pass


class ReportCache:
    def __init__(self, s3=None, bucket=None, cdn_url=None, secret=None):
        self.s3 = s3 or boto3.client(
            "s3", endpoint_url=os.environ["S3_ENDPOINT_URL"],
            aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key=os.environ["S3_SECRET_KEY"],
            region_name="us-east-1",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                          connect_timeout=3, read_timeout=5, retries={"max_attempts": 1}),
        )
        self.bucket = bucket or os.getenv("S3_BUCKET", "reports")
        self.cdn_url = (cdn_url or os.getenv("CDN_PUBLIC_URL", "http://localhost:8082")).rstrip("/")
        self.secret = secret or os.environ["CDN_SIGNING_SECRET"]
        if len(self.secret) < 32:
            raise ValueError("CDN_SIGNING_SECRET must contain at least 32 characters")
        # Блокировки исключают повторную генерацию в одном процессе API.
        self.locks = [Lock() for _ in range(64)]

    def snapshot(self):
        obj = self.s3.get_object(Bucket=self.bucket, Key="metadata/current.json")
        with obj["Body"] as body:
            version = json.load(body)["snapshot_id"]
        if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
            raise ValueError("Invalid snapshot marker")
        return version

    def exists(self, key):
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def get(self, issuer, subject, reports):
        owner = hashlib.sha256(json.dumps([issuer, subject], separators=(",", ":")).encode()).hexdigest()
        with self.locks[int(owner[:2], 16) % len(self.locks)]:
            version = self.snapshot()
            key = f"reports/v1/{version}/{owner}.json"
            if not self.exists(key):
                report = reports.get(issuer, subject)
                if report is None:
                    return None
                # ETL могла обновить витрину раньше маркера в S3.
                if report["snapshot_id"] != version:
                    raise SnapshotChanged()
                self.s3.put_object(
                    Bucket=self.bucket, Key=key, Body=json.dumps(jsonable_encoder(report)).encode(),
                    ContentType="application/json", CacheControl="private, no-store",
                )
        expires = int(time.time()) + 300
        path = "/" + key
        token = jwt.encode({"path": path, "exp": expires, "aud": "reports-cdn"}, self.secret, algorithm="HS256")
        return {"url": f"{self.cdn_url}{path}?token={token}",
                "expires_at": expires, "snapshot_id": version}

    def origin(self, uri):
        parsed = urlsplit(uri)
        if not re.fullmatch(r"/reports/v1/[0-9a-f]{64}/[0-9a-f]{64}\.json", parsed.path):
            raise ValueError("Invalid report path")
        query = parse_qs(parsed.query, strict_parsing=True)
        if set(query) != {"token"} or len(query["token"]) != 1:
            raise ValueError("Invalid CDN token")
        claims = jwt.decode(query["token"][0], self.secret, algorithms=["HS256"], audience="reports-cdn",
                            options={"require": ["exp", "path", "aud"]})
        if claims["path"] != parsed.path:
            raise ValueError("Token belongs to another report")
        # Внутреннюю ссылку на закрытый бакет получает только Nginx.
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": parsed.path[1:]}, ExpiresIn=60,
        )
