"""Render API provisioning for private File Sharing and Link Sharing bot images."""
from __future__ import annotations

import os
import re
from urllib.parse import quote

import httpx


class RenderAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class RenderProvisioner:
    """Creates and manages image-backed Render Background Workers."""

    API_BASE = "https://api.render.com/v1"
    PRODUCT_REPOSITORIES = {
        "file": "https://github.com/Portalsbot/File-Share-Bot",
        "link": "https://github.com/Portalsbot/link-sharing-bot",
    }
    DEFAULT_IMAGES = {
        "file": "ghcr.io/portalsbot/file-share-bot:latest",
        "link": "ghcr.io/portalsbot/link-sharing-bot:latest",
    }
    RESERVED_ENV = {
        "BOT_TOKEN", "DATABASE_URL", "OWNER_ID", "ADMINS", "CLONE_ID",
        "CONFIG_FILE", "BRANDING_IMAGE_URL", "BRANDING_IMAGE_PATH",
        "SHORTENER_ENCRYPTION_KEY",
    }

    def __init__(self):
        self.api_key = os.getenv("RENDER_API_KEY", "").strip()
        self.workspace_id = (
            os.getenv("RENDER_WORKSPACE_ID") or os.getenv("RENDER_OWNER_ID") or ""
        ).strip()
        self.registry_credential_id = os.getenv("RENDER_REGISTRY_CREDENTIAL_ID", "").strip()
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.owner_id = os.getenv("OWNER_ID", "").strip()
        self.admin_ids = os.getenv("ADMIN_IDS", "").replace(",", " ").strip()
        self.branding_url = os.getenv(
            "BRANDING_IMAGE_URL",
            "https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png",
        ).strip()
        self.file_image = os.getenv("FILE_SHARING_IMAGE", self.DEFAULT_IMAGES["file"]).strip()
        self.link_image = os.getenv("LINK_SHARING_IMAGE", self.DEFAULT_IMAGES["link"]).strip()
        self.file_repo = os.getenv("FILE_SHARING_REPO_URL", self.PRODUCT_REPOSITORIES["file"]).strip()
        self.link_repo = os.getenv("LINK_SHARING_REPO_URL", self.PRODUCT_REPOSITORIES["link"]).strip()
        self.region = os.getenv("RENDER_REGION", "singapore").strip().lower()
        self.plan = os.getenv("RENDER_WORKER_PLAN", "starter").strip().lower()
        self.channel_url = os.getenv("CLONE_CHANNEL_URL", "").strip()
        self.storage_channel_id = os.getenv("CLONE_STORAGE_CHANNEL_ID", "").strip()
        self.default_auto_delete = os.getenv("CLONE_DEFAULT_AUTO_DELETE", "0").strip()
        self.max_files_per_user = os.getenv("CLONE_MAX_FILES_PER_USER", "50").strip()
        self.shortener_allowed_hosts = os.getenv("LINK_SHORTENER_ALLOWED_HOSTS", "").strip()

    def repository_for(self, product: str) -> str:
        if product not in self.PRODUCT_REPOSITORIES:
            raise ValueError(f"Unsupported clone product: {product}")
        return self.file_repo if product == "file" else self.link_repo

    def image_for(self, product: str) -> str:
        if product not in self.DEFAULT_IMAGES:
            raise ValueError(f"Unsupported clone product: {product}")
        return self.file_image if product == "file" else self.link_image

    def validate_configuration(self) -> None:
        missing = [
            name for name, value in (
                ("RENDER_API_KEY", self.api_key),
                ("RENDER_WORKSPACE_ID", self.workspace_id),
                ("RENDER_REGISTRY_CREDENTIAL_ID", self.registry_credential_id),
                ("DATABASE_URL", self.database_url),
                ("OWNER_ID", self.owner_id),
            ) if not value
        ]
        if missing:
            raise RuntimeError("Missing Render provisioning configuration: " + ", ".join(missing))
        if not self.file_image or not self.link_image:
            raise RuntimeError("Both FILE_SHARING_IMAGE and LINK_SHARING_IMAGE must be configured.")
        if not self.file_repo.startswith("https://github.com/") or not self.link_repo.startswith("https://github.com/"):
            raise RuntimeError("Both product repository URLs must be HTTPS GitHub repository URLs.")

    async def _request(self, method: str, path: str, *, params=None, payload=None):
        self.validate_configuration()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"{self.API_BASE}{path}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=10.0)) as client:
            response = await client.request(
                method, url, headers=headers, params=params, json=payload
            )
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("message") or body.get("error") or body.get("code") or "Render API request failed"
            except (ValueError, AttributeError):
                detail = "Render API request failed"
            # Never include request headers or secrets in an exception/log message.
            raise RenderAPIError(response.status_code, f"Render API HTTP {response.status_code}: {str(detail)[:240]}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _service_id(data) -> str | None:
        if not isinstance(data, dict):
            return None
        service = data.get("service") if isinstance(data.get("service"), dict) else data
        service_id = service.get("id") if isinstance(service, dict) else None
        return str(service_id) if service_id else None

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-") or "bot"

    def _service_name(self, product: str, clone_id: str) -> str:
        name = f"clone-{product}-{self._slug(clone_id)}"
        return name[:60].rstrip("-")

    def _worker_environment(self, product: str, clone_id: str, token: str, owner_id: int,
                            extra_environment: dict[str, str] | None = None) -> list[dict[str, str]]:
        values = {
            "BOT_TOKEN": token,
            "DATABASE_URL": self.database_url,
            "OWNER_ID": str(owner_id),
            "ADMINS": self.admin_ids,
            "CLONE_ID": clone_id,
            "BRANDING_IMAGE_URL": self.branding_url,
            "BRANDING_IMAGE_PATH": "",
            "SMALL_CAPS": "true",
            "DEFAULT_AUTO_DELETE": self.default_auto_delete,
            "MAX_FILES_PER_USER": self.max_files_per_user,
        }
        if self.channel_url:
            values["CHANNEL_URL"] = self.channel_url
        if self.storage_channel_id:
            values["STORAGE_CHANNEL_ID"] = self.storage_channel_id
        custom_environment = dict(extra_environment or {})
        if product == "link":
            from cryptography.fernet import Fernet
            # The key is generated once per clone and persisted encrypted by Clone Manager.
            # On redeploy the stored value is supplied back through extra_environment.
            values["SHORTENER_ENCRYPTION_KEY"] = custom_environment.pop(
                "SHORTENER_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii")
            )
            if self.shortener_allowed_hosts:
                values["SHORTENER_ALLOWED_HOSTS"] = self.shortener_allowed_hosts

        for key, value in custom_environment.items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", key):
                raise ValueError(f"Invalid environment variable name: {key!r}")
            if key in self.RESERVED_ENV:
                raise ValueError(f"{key} is managed by Clone Manager and cannot be overridden.")
            values[key] = str(value)
        return [{"key": key, "value": str(value)} for key, value in values.items()]

    async def _find_service(self, name: str) -> str | None:
        data = await self._request(
            "GET", "/services",
            params={"ownerId": self.workspace_id, "name": name, "limit": 100},
        )
        if not isinstance(data, list):
            return None
        for item in data:
            service = item.get("service", item) if isinstance(item, dict) else {}
            if isinstance(service, dict) and service.get("name") == name and service.get("id"):
                return str(service["id"])
        return None

    async def _create_service(self, product: str, clone_id: str, image_ref: str,
                              environment: list[dict[str, str]], *, region=None, plan=None) -> str:
        name = self._service_name(product, clone_id)
        existing_id = await self._find_service(name)
        if existing_id:
            service_path = f"/services/{quote(existing_id, safe='')}"
            await self._request("PUT", f"{service_path}/env-vars", payload=environment)
            await self._request("PATCH", service_path, payload={
                "image": {
                    "ownerId": self.workspace_id,
                    "imagePath": image_ref,
                    "registryCredentialId": self.registry_credential_id,
                },
                "serviceDetails": {"plan": (plan or self.plan).lower()},
            })
            await self._request(
                "POST", f"{service_path}/deploys",
                payload={"clearCache": "do_not_clear"},
            )
            return existing_id

        payload = {
            "type": "background_worker",
            "name": name,
            "ownerId": self.workspace_id,
            "autoDeployTrigger": "off",
            "image": {
                "ownerId": self.workspace_id,
                "imagePath": image_ref,
                "registryCredentialId": self.registry_credential_id,
            },
            "envVars": environment,
            "serviceDetails": {
                "region": (region or self.region).lower(),
                "plan": (plan or self.plan).lower(),
                "numInstances": 1,
            },
        }
        data = await self._request("POST", "/services", payload=payload)
        service_id = self._service_id(data)
        if not service_id:
            raise RuntimeError("Render accepted the service request but did not return a service ID.")
        return service_id

    async def create(self, product: str, clone_id: str, bot_token: str, owner_id: int,
                     *, image_ref=None, extra_environment=None, region=None, plan=None):
        if product not in self.DEFAULT_IMAGES:
            raise ValueError(f"Unsupported clone product: {product}")
        image = (image_ref or self.image_for(product)).strip()
        env = self._worker_environment(product, clone_id, bot_token, owner_id, extra_environment)
        return await self._create_service(product, clone_id, image, env, region=region, plan=plan)

    async def redeploy(self, product: str, clone_id: str, bot_token: str, owner_id: int,
                       *, current_service_id: str | None, image_ref=None, extra_environment=None,
                       region=None, plan=None):
        if not current_service_id:
            return await self.create(
                product, clone_id, bot_token, owner_id, image_ref=image_ref,
                extra_environment=extra_environment, region=region, plan=plan,
            )
        image = (image_ref or self.image_for(product)).strip()
        env = self._worker_environment(product, clone_id, bot_token, owner_id, extra_environment)
        service_path = f"/services/{quote(current_service_id, safe='')}"
        try:
            await self._request("PUT", f"{service_path}/env-vars", payload=env)
            await self._request("PATCH", service_path, payload={
                "image": {
                    "ownerId": self.workspace_id,
                    "imagePath": image,
                    "registryCredentialId": self.registry_credential_id,
                },
                "serviceDetails": {"plan": (plan or self.plan).lower()},
            })
            await self._request("POST", f"{service_path}/deploys", payload={"clearCache": "do_not_clear"})
            return current_service_id
        except RenderAPIError as exc:
            if exc.status_code != 404:
                raise
            # The service may have been removed manually from Render. Recreate it.
            return await self.create(
                product, clone_id, bot_token, owner_id, image_ref=image,
                extra_environment=extra_environment, region=region, plan=plan,
            )

    async def stop(self, service_id: str):
        return await self._request("POST", f"/services/{quote(service_id, safe='')}/suspend", payload={})

    async def restart(self, service_id: str):
        path = f"/services/{quote(service_id, safe='')}"
        service = await self._request("GET", path)
        action = "resume" if isinstance(service, dict) and service.get("suspended") == "suspended" else "restart"
        return await self._request("POST", f"{path}/{action}", payload={})

    async def delete(self, service_id: str):
        return await self._request("DELETE", f"/services/{quote(service_id, safe='')}")

    async def status(self, service_id: str) -> str:
        try:
            service = await self._request("GET", f"/services/{quote(service_id, safe='')}")
            if isinstance(service, dict) and service.get("suspended") == "suspended":
                return "stopped"
            deploys = await self._request(
                "GET", f"/services/{quote(service_id, safe='')}/deploys",
                params={"limit": 1},
            )
        except RenderAPIError:
            return "unknown"
        if isinstance(deploys, list) and deploys:
            latest = deploys[0].get("deploy", deploys[0]) if isinstance(deploys[0], dict) else {}
            state = str(latest.get("status", "")).lower() if isinstance(latest, dict) else ""
            if state == "live":
                return "running"
            if state in {"build_failed", "update_failed", "pre_deploy_failed", "deactivated"}:
                return "failed"
            if state in {"canceled", "cancelled"}:
                return "stopped"
            if state:
                return "provisioning"
        return "provisioning"

    async def ping(self) -> bool:
        await self._request(
            "GET", "/services", params={"ownerId": self.workspace_id, "limit": 1}
        )
        return True
