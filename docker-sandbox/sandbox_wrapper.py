import docker
import tempfile
import os
import logging

logger = logging.getLogger(__name__)


class SafeSandbox:
    def __init__(self):
        self.client = docker.from_env()
        self.image_name = "sandbox:latest"

    def _ensure_image(self):
        try:
            self.client.images.get(self.image_name)
        except docker.errors.ImageNotFound:
            dockerfile_path = os.path.join(os.path.dirname(__file__), "Dockerfile.sandbox")
            self.client.images.build(path=os.path.dirname(dockerfile_path), tag=self.image_name)
            logger.info("تم بناء صورة الساندبوكس")

    def execute(self, code: str, timeout_seconds: int = 5) -> dict:
        self._ensure_image()

        try:
            container = self.client.containers.run(
                self.image_name,
                command=["python", "-c", code],
                network_disabled=True,
                mem_limit="256m",
                cpu_quota=50000,
                read_only=True,
                remove=True,
                detach=True
            )

            result = container.wait(timeout=timeout_seconds)
            logs = container.logs(stdout=True, stderr=True).decode('utf-8')

            container.stop()
            container.remove()

            return {
                "success": result["StatusCode"] == 0,
                "output": logs,
                "error": None if result["StatusCode"] == 0 else f"Exit code: {result['StatusCode']}"
            }

        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}
