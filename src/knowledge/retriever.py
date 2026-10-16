import boto3
from botocore.exceptions import ClientError
from typing import List, Tuple
from core.config import config
from core.constants import region


class RAG:
    """Retrieve context from Amazon Bedrock Knowledge Base"""

    def __init__(self):
        self.session = boto3.Session(
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=region.AP_SOUTHEAST_1,
        )

    def _create_client(self, service_name: str = "bedrock-agent-runtime"):
        if config.AWS_ROLE_ARN:
            sts_client = self.session.client("sts")
            assumed_role = sts_client.assume_role(
                RoleArn=config.AWS_ROLE_ARN, RoleSessionName="BedrockSession"
            )
            credentials = assumed_role["Credentials"]
            return boto3.client(
                service_name=service_name,
                region_name=region.AP_SOUTHEAST_1,
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )
        return self.session.client(
            service_name=service_name, region_name=region.AP_SOUTHEAST_1
        )

    def retrieve_context(
        self, query: str, kbId: str, numberOfResults: int = 5
    ) -> List[dict]:
        # Initate bedrock client to retrieve context
        response = self._create_client().retrieve(
            retrievalQuery={"text": query},
            knowledgeBaseId=kbId,
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": numberOfResults,
                }
            },
        )
        return response["retrievalResults"]

    def get_contexts(
        self, retrieval_results: List[dict]
    ) -> Tuple[List[str], List[str], List[float]]:
        contexts = []
        sources = []
        scores = []
        for result in retrieval_results:
            contexts.append(result["content"]["text"])
            sources.append(result["location"]["s3Location"]["uri"])
            scores.append(result["score"])

        # Get unique sources
        unique_sources = list(set(sources))
        return contexts, unique_sources, scores

    def _parse_s3_uri(self, s3_uri: str) -> Tuple[str, str]:
        if s3_uri.startswith("s3://"):
            s3_uri = s3_uri[5:]
        else:
            raise ValueError("Invalid S3 Uri")
        bucket_name, object_key = s3_uri.split("/", 1)
        return bucket_name, object_key

    def _create_presigned_url(
        self, bucket_name: str, object_name: str, expiration: int = 7200
    ):
        s3_client = boto3.client("s3")
        try:
            response = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": object_name},
                ExpiresIn=expiration,
            )
        except ClientError:
            return None
        return response

    def generate_presigned_urls(
        self, s3_uris: List[str], expiration: int = 7200
    ) -> List[str]:
        presigned_urls = []
        for s3_uri in s3_uris:
            bucket_name, object_key = self._parse_s3_uri(s3_uri)
            presigned_url = self._create_presigned_url(
                bucket_name, object_key, expiration
            )
            if presigned_url:
                presigned_urls.append(presigned_url)
        return presigned_urls
