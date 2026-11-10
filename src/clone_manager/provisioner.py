"""Docker provisioning adapter.

Production note: mount CLONE_SECRET_DIR from a root-controlled host volume. The per-clone
config file contains plaintext secrets while the container is running, so protect the host
filesystem and Docker socket as highly privileged infrastructure.
"""
from __future__ import annotations
import json, os, re
from pathlib import Path
import docker

class DockerProvisioner:
    def __init__(self):
        self.client=docker.from_env()
        self.secret_root=Path(os.getenv("CLONE_SECRET_DIR","/var/lib/clone-manager/secrets"))
        self.database_url=os.environ["DATABASE_URL"]
        self.branding_url=os.getenv("BRANDING_IMAGE_URL","https://raw.githubusercontent.com/Portalsbot/image/main/photo_2026-11-01_20-42-48.jpg")
        self.file_image=os.getenv("FILE_SHARING_IMAGE","")
        self.link_image=os.getenv("LINK_SHARING_IMAGE","")
        self.network=os.getenv("CLONE_DOCKER_NETWORK") or None
        self.registry_user=os.getenv("GHCR_USERNAME")
        self.registry_token=os.getenv("GHCR_TOKEN")

    async def create(self,product:str,clone_id:str,bot_token:str,owner_id:int)->str:
        image=self.file_image if product=="file" else self.link_image
        if not image: raise RuntimeError(f"Image not configured for product: {product}")
        if self.registry_user and self.registry_token:
            self.client.login(username=self.registry_user,password=self.registry_token,registry="ghcr.io")
        self.client.images.pull(image)
        self.secret_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(self.secret_root,0o700)
        safe=re.sub(r"[^a-zA-Z0-9_.-]","-",clone_id)
        secret_dir=self.secret_root/safe
        secret_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(secret_dir,0o700)
        config_file=secret_dir/"config.json"
        config={"BOT_TOKEN":bot_token,"DATABASE_URL":self.database_url,"CLONE_ID":clone_id,
                "OWNER_ID":str(owner_id),"BRANDING_IMAGE_URL":self.branding_url,"SMALL_CAPS":"true"}
        config_file.write_text(json.dumps(config),encoding="utf-8")
        os.chmod(config_file,0o600)
        container=self.client.containers.run(
            image,detach=True,name=f"tg-{safe}",
            environment={"CONFIG_FILE":"/run/secrets/app-config.json"},
            volumes={str(config_file):{"bind":"/run/secrets/app-config.json","mode":"ro"}},
            network=self.network, restart_policy={"Name":"unless-stopped"},
            labels={"app":"telegram-clone","clone_id":clone_id,"product":product},
        )
        return container.id

    async def stop(self,container_id:str):
        self.client.containers.get(container_id).stop(timeout=15)

    async def restart(self,container_id:str):
        self.client.containers.get(container_id).restart(timeout=15)

    async def status(self, container_id: str) -> str:
        """Return the current Docker state; unknown is never reported as stopped."""
        try:
            container=self.client.containers.get(container_id)
            container.reload()
            state=(container.attrs.get("State") or {}).get("Status","unknown")
            return "running" if state=="running" else "stopped" if state in {"exited","created","dead"} else "unknown"
        except Exception:
            return "unknown"
