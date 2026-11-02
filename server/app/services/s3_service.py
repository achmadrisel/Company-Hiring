import boto3
from botocore.exceptions import ClientError
from typing import Optional, List
from app.core.config import get_settings

settings = get_settings()

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION,
            endpoint_url=settings.S3_ENDPOINT_URL
        )
        self.bucket_name = settings.S3_BUCKET_NAME
        self.gateway_url = "https://slimy-amethyst-bee.myfilebase.com/ipfs"

    def upload_file(self, file_data: bytes, file_name: str, content_type: str = "application/octet-stream") -> Optional[str]:
        """Upload file ke Filebase dan kembalikan URL IPFS Gateway"""
        try:
            response = self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_name,
                Body=file_data,
                ContentType=content_type
            )

            cid = response.get('ResponseMetadata', {}).get('HTTPHeaders', {}).get('x-amz-meta-cid')

            if cid:
                return f"{self.gateway_url}/{cid}"
            
            return None
        except ClientError as e:
            print(f"Error uploading file: {e}")
            return None
        

    def delete_file(self, file_name: str) -> bool:
        """
        Delete file from S3
        Returns: True if success, False if failed
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=file_name)
            return True
        except ClientError as e:
            print(f"Error deleting file: {e}")
            return False
        
    def file_exists(self, file_name: str) -> bool:
        """
        Check if file exists in S3
        Returns: True if exists, False if not exists
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=file_name)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            print(f"Error checking file existence: {e}")
            return False
        
    def get_file_url(self, file_name: str) -> Optional[str]:
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=file_name)
            cid = response.get('Metadata', {}).get('cid') or response.get('ResponseMetadata', {}).get('HTTPHeaders', {}).get('x-amz-meta-cid')

            if cid:
                return f"{self.gateway_url}/{cid}"
            return None
        except ClientError as e:
            print(f"Error getting file URL: {e}")
            return None
        
s3_service = S3Service()