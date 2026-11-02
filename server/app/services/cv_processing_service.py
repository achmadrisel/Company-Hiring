from typing import Tuple, List, Dict
import json
import asyncio
import litellm

import unstructured_client
from unstructured_client.models import operations, shared

from app.services.embedding_service import embedding_service
from app.core.config import get_settings

settings = get_settings()

async def _extract_json_from_text(extracted_text: str) -> Dict:
    prompt = f"""
You are an expert HR resume parser. Extract the candidate's CV details into a strict JSON matching this schema exactly:
{{
  "candidate_summary": "<Compose a strong professional summary based on the CV>",
  "skills": ["<strings>"],
  "education": ["<strings>"],
  "work_experiences": ["<strings>"],
  "projects": ["<strings>"],
  "certifications": ["<strings>"]
}}
Return only valid JSON, no markdown blocks.

CV Text: 
{extracted_text}
"""
    try:
        response = await litellm.acompletion(
            model=f"openrouter/{settings.LLM_MODEL}",
            messages=[{"role": "user", "content": prompt}],
            api_key=settings.OPENROUTER_API_KEY,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()

        return json.loads(content)
    except Exception as e:
        print(f"LLM Json extraction failed: {e}")
        return {
            "candidate_summary": "Extracted text summary failed.",
            "skills": [],
            "education": [],
            "work_experiences": [],
            "projects": [],
            "certifications": []
        }


class CVProcessingService:
    def __init__(self):
        self.client = unstructured_client.UnstructuredClient(
            api_key_auth=settings.UNSTRUCTURED_API_KEY,
            server_url=settings.UNSTRUCTURED_API_URL,
        )

    async def process_cv(self, file_data: bytes, file_name: str) -> Tuple[Dict, List[float], str]:
        return await self._process_via_sdk(file_data, file_name)

    async def _process_via_sdk(self, file_data: bytes, file_name: str) -> Tuple[Dict, List[float], str]:
        loop = asyncio.get_event_loop()

        create_req = operations.CreateJobRequest(
            body_create_job=shared.BodyCreateJob(
                request_data=json.dumps({
                    "job_nodes": [
                        {
                            "name": "Partitioner",
                            "type": "partition",
                            "subtype": "vlm",
                            "settings": {
                                "is_dynamic": True,
                                "allow_fast": True,
                            },
                        }
                    ]
                }),
                input_files=[
                    shared.InputFiles(
                        content=file_data,
                        file_name=file_name,
                    )
                ],
            )
        )

        create_res = await loop.run_in_executor(
            None, lambda: self.client.jobs.create_job(request=create_req)
        )
        job_id = create_res.job_information.id

        poll_interval = 2
        max_retries = 60
        for _ in range(max_retries):
            await asyncio.sleep(poll_interval)
            get_res = await loop.run_in_executor(
                None,
                lambda jid=job_id: self.client.jobs.get_job(
                    request=operations.GetJobRequest(job_id=jid)
                ),
            )
            job_info = get_res.job_information

            if job_info.status == shared.JobStatus.COMPLETED:
                break
            if job_info.status in (
                shared.JobStatus.FAILED,
                shared.JobStatus.STOPPED,
            ):
                raise RuntimeError(
                    f"Unstructured job {job_id} ended with status {job_info.status}"
                )
        else:
            raise TimeoutError(f"Unstructured job {job_id} did not complete in time")

        file_id = job_info.output_node_files[0].file_id
        download_res = await loop.run_in_executor(
            None,
            lambda: self.client.jobs.download_job_output(
                request=operations.DownloadJobOutputRequest(
                    job_id=job_id, file_id=file_id
                )
            ),
        )

        elements = download_res.any if download_res.any else []
        if isinstance(elements, dict):
            elements = [elements]
        extracted_text = "\n".join(
            el.get("text", "") for el in elements if isinstance(el, dict) and el.get("text")
        )

        if not extracted_text.strip():
            extracted_text = "No text could be extracted from this CV."

        resume_json = await _extract_json_from_text(extracted_text)
        embedding = embedding_service.encode(extracted_text)

        return resume_json, embedding, extracted_text


cv_processing_service = CVProcessingService()
